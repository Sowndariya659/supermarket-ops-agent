"""Billing service managing multi-turn draft bills, GST calculations, atomic finalization, and oversell protection."""

from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from app.database.models import Bill, Customer
from app.database.repositories import (
    BillingRepository,
    InventoryRepository,
    ProductRepository,
    KhataRepository,
    InsufficientStockError,
    round_money,
)


class BillingService:
    def __init__(self, session: Session):
        self.session = session
        self.bill_repo = BillingRepository(session)
        self.inventory_repo = InventoryRepository(session)
        self.product_repo = ProductRepository(session)
        self.khata_repo = KhataRepository(session)

    def get_or_create_draft(
        self,
        chat_id: int,
        payment_mode: Optional[str] = None,
        customer_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fetch active draft bill for chat or create a new one."""
        draft = self.bill_repo.get_draft_by_chat(chat_id)
        customer_id = None
        if customer_name:
            cust = self.khata_repo.get_or_create_customer(customer_name)
            customer_id = cust.id

        if not draft:
            mode = payment_mode or "UPI"
            draft = self.bill_repo.create_draft(chat_id=chat_id, payment_mode=mode, customer_id=customer_id)
            self.session.commit()
        else:
            if payment_mode:
                draft.payment_mode = payment_mode
            if customer_id:
                draft.customer_id = customer_id
            self.session.commit()

        return draft.to_dict()

    def get_current_bill(self, chat_id: int) -> Optional[Dict[str, Any]]:
        """Get the current active draft for a chat."""
        draft = self.bill_repo.get_draft_by_chat(chat_id)
        return draft.to_dict() if draft else None

    def add_item(
        self,
        chat_id: int,
        product_id: int,
        quantity: float,
        unit_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Add an item to the current draft bill. Stock is NOT decremented here."""
        if quantity <= 0:
            raise ValueError("Item quantity must be positive.")

        draft = self.bill_repo.get_draft_by_chat(chat_id)
        if not draft:
            draft = self.bill_repo.create_draft(chat_id=chat_id)

        qty_dec = Decimal(str(quantity))
        price_dec = Decimal(str(unit_price)) if unit_price is not None else None

        self.bill_repo.add_or_update_item(
            bill_id=draft.id,
            product_id=product_id,
            quantity=qty_dec,
            unit_price=price_dec,
            replace_quantity=False,
        )
        self.session.commit()
        # Refresh to get recalculated totals
        self.session.refresh(draft)
        return draft.to_dict()

    def update_item(self, chat_id: int, product_id: int, quantity: float) -> Dict[str, Any]:
        """Update or replace the quantity of an item in the draft bill."""
        draft = self.bill_repo.get_draft_by_chat(chat_id)
        if not draft:
            raise ValueError("No active draft bill found for this chat.")

        qty_dec = Decimal(str(quantity))
        self.bill_repo.add_or_update_item(
            bill_id=draft.id,
            product_id=product_id,
            quantity=qty_dec,
            replace_quantity=True,
        )
        self.session.commit()
        self.session.refresh(draft)
        return draft.to_dict()

    def remove_item(self, chat_id: int, product_id: int) -> Dict[str, Any]:
        """Remove an item from the draft bill."""
        draft = self.bill_repo.get_draft_by_chat(chat_id)
        if not draft:
            raise ValueError("No active draft bill found for this chat.")

        removed = self.bill_repo.remove_item(bill_id=draft.id, product_id=product_id)
        self.session.commit()
        self.session.refresh(draft)
        return {
            "removed": removed,
            "bill": draft.to_dict(),
        }

    def finalize_bill(
        self,
        chat_id: int,
        payment_mode: Optional[str] = None,
        payment_ref: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Atomically commit the draft bill and decrement stock.
        Guarantees:
        1. Stock safety (zero overselling) via atomic row updates.
        2. Rollback on any failure.
        3. Idempotency against duplicate finalization attempts.
        4. Automatic ledger entry if payment is KHATA.
        """
        # 1. Idempotency check if key provided
        if idempotency_key:
            existing = self.session.query(Bill).filter(Bill.idempotency_key == idempotency_key).first()
            if existing and existing.status == "FINALIZED":
                return {
                    "already_finalized": True,
                    "bill": existing.to_dict(),
                }

        draft = self.bill_repo.get_draft_by_chat(chat_id)
        if not draft:
            raise ValueError("No active draft bill found to finalize.")

        if not draft.items:
            raise ValueError("Cannot finalize an empty bill. Please add items first.")

        # Update payment mode if provided
        if payment_mode:
            draft.payment_mode = payment_mode.upper()
        if payment_ref:
            draft.payment_reference = payment_ref
        if idempotency_key:
            draft.idempotency_key = idempotency_key

        # 2. Sort items by product_id to ensure deterministic locking order and prevent deadlocks
        sorted_items = sorted(draft.items, key=lambda it: it.product_id)

        # 3. Atomically decrement stock for each item
        for item in sorted_items:
            success = self.inventory_repo.decrement_stock_atomic(
                product_id=item.product_id,
                quantity=item.quantity,
            )
            if not success:
                # Get current stock to give a friendly error
                current_stock = self.inventory_repo.get_stock(item.product_id)
                self.session.rollback()
                raise InsufficientStockError(
                    product_id=item.product_id,
                    product_name=item.product.name,
                    requested=item.quantity,
                    available=current_stock,
                )

        # 4. Handle KHATA payment ledger debit
        if draft.payment_mode == "KHATA":
            if not draft.customer_id:
                self.session.rollback()
                raise ValueError("Customer must be linked to bill when paying via Khata.")
            
            self.khata_repo.add_transaction(
                customer_id=draft.customer_id,
                transaction_type="CREDIT",
                amount=draft.grand_total,
                reference=f"Bill #{draft.bill_number}",
            )

        # 5. Mark bill finalized
        draft.status = "FINALIZED"
        draft.finalized_at = datetime.utcnow()
        self.session.commit()
        self.session.refresh(draft)

        return {
            "already_finalized": False,
            "bill": draft.to_dict(),
        }

    def cancel_current_draft(self, chat_id: int) -> Dict[str, Any]:
        """Cancel current open draft without decrementing any stock."""
        draft = self.bill_repo.get_draft_by_chat(chat_id)
        if not draft:
            return {"cancelled": False, "message": "No active draft bill found."}

        draft.status = "CANCELLED"
        draft.finalized_at = datetime.utcnow()
        self.session.commit()
        return {"cancelled": True, "bill_number": draft.bill_number}
