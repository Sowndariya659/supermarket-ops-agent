"""Database repositories with atomic transactions, row locking, and Decimal math."""

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import or_, func, and_
from app.database.models import (
    Product,
    Inventory,
    Customer,
    Bill,
    BillItem,
    KhataTransaction,
    OwnerPreference,
    ProcessedTelegramUpdate,
)


class InsufficientStockError(Exception):
    def __init__(self, product_id: int, product_name: str, requested: Decimal, available: Decimal):
        self.product_id = product_id
        self.product_name = product_name
        self.requested = requested
        self.available = available
        super().__init__(
            f"Insufficient stock for '{product_name}' (ID: {product_id}). "
            f"Requested {requested}, but only {available} available."
        )


class BelowCostPriceError(Exception):
    def __init__(self, product_name: str, sell_price: Decimal, cost_price: Decimal):
        self.product_name = product_name
        self.sell_price = sell_price
        self.cost_price = cost_price
        super().__init__(
            f"Cannot sell '{product_name}' at ₹{sell_price}, which is below cost price ₹{cost_price}."
        )


# --- Utility GST Calculations ---

def round_money(val: Decimal) -> Decimal:
    return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_item_taxes(unit_price: Decimal, quantity: Decimal, gst_rate: Decimal) -> Tuple[Decimal, Decimal, Decimal, Decimal]:
    """
    Calculate taxable amount, cgst, sgst, and total for an item where unit_price is MRP (tax inclusive).
    Returns (taxable_amount, cgst, sgst, total).
    """
    total = round_money(unit_price * quantity)
    if gst_rate <= 0:
        return total, Decimal("0.00"), Decimal("0.00"), total

    multiplier = Decimal("1.00") + (gst_rate / Decimal("100.00"))
    taxable_amount = round_money(total / multiplier)
    total_tax = total - taxable_amount
    cgst = round_money(total_tax / Decimal("2.00"))
    sgst = total_tax - cgst  # Ensures cgst + sgst == total_tax exactly
    return taxable_amount, cgst, sgst, total


# --- Product & Inventory Repository ---

class ProductRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, product_id: int) -> Optional[Product]:
        return self.session.query(Product).filter(Product.id == product_id).first()

    def get_by_sku(self, sku: str) -> Optional[Product]:
        return self.session.query(Product).filter(Product.sku == sku).first()

    def list_all(self, limit: int = 50) -> List[Product]:
        """List all available products in the catalog."""
        return self.session.query(Product).order_by(Product.name.asc()).limit(limit).all()

    def search(self, query: str, limit: int = 10) -> List[Product]:
        """Search products by name, brand, or SKU with synonym and fuzzy matching."""
        import difflib
        raw_query = query.strip().lower()

        # Dictionary of common Kirana synonyms and typos
        synonyms = {
            "buter": "butter",
            "makhan": "butter",
            "cheeni": "sugar",
            "sakkar": "sugar",
            "chawal": "rice",
            "aata": "atta",
            "gehu": "atta",
            "tel": "oil",
            "namak": "salt",
            "maggie": "maggi",
            "daal": "dal",
            "sabun": "surf",
            "detergent": "surf",
            "biscuit": "parle",
        }
        clean_terms = []
        for word in raw_query.split():
            clean_terms.append(synonyms.get(word, word))
        search_str = " ".join(clean_terms)

        term = f"%{search_str}%"
        matches = (
            self.session.query(Product)
            .filter(
                or_(
                    Product.name.ilike(term),
                    Product.brand.ilike(term),
                    Product.sku.ilike(term),
                )
            )
            .limit(limit)
            .all()
        )
        if matches:
            return matches

        # Fallback to fuzzy substring / close match across all products
        all_products = self.list_all(limit=100)
        fuzzy_matches = []
        for p in all_products:
            p_name_lower = p.name.lower()
            # Check if any clean term is a substring or close match
            for t in clean_terms:
                if len(t) >= 3 and (t in p_name_lower or difflib.SequenceMatcher(None, t, p_name_lower).ratio() > 0.5):
                    fuzzy_matches.append(p)
                    break

        return fuzzy_matches[:limit]

    def create(
        self,
        name: str,
        sku: str,
        cost_price: Decimal,
        sell_price: Decimal,
        mrp: Decimal,
        gst_rate: Decimal,
        unit: str = "packet",
        brand: Optional[str] = None,
        is_loose: bool = False,
        hsn_code: str = "1904",
        reorder_level: Decimal = Decimal("10.000"),
        initial_stock: Decimal = Decimal("0.000"),
    ) -> Product:
        product = Product(
            name=name.strip(),
            sku=sku.strip().upper(),
            brand=brand.strip() if brand else None,
            unit=unit.strip().lower(),
            is_loose=is_loose,
            hsn_code=hsn_code.strip(),
            gst_rate=gst_rate,
            cost_price=cost_price,
            sell_price=sell_price,
            mrp=mrp,
            reorder_level=reorder_level,
        )
        self.session.add(product)
        self.session.flush()

        inventory = Inventory(
            product_id=product.id,
            quantity=initial_stock,
        )
        self.session.add(inventory)
        self.session.flush()
        return product


class InventoryRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_stock(self, product_id: int) -> Decimal:
        inv = self.session.query(Inventory).filter(Inventory.product_id == product_id).first()
        return inv.quantity if inv else Decimal("0.000")

    def receive_stock(
        self,
        product_id: int,
        quantity: Decimal,
        cost_price: Optional[Decimal] = None,
        mrp: Optional[Decimal] = None,
    ) -> Inventory:
        inv = self.session.query(Inventory).filter(Inventory.product_id == product_id).with_for_update().first()
        if not inv:
            inv = Inventory(product_id=product_id, quantity=Decimal("0.000"))
            self.session.add(inv)
        
        inv.quantity += quantity
        inv.updated_at = datetime.utcnow()

        # Optionally update product cost or mrp if supplier changed pricing
        product = self.session.query(Product).filter(Product.id == product_id).first()
        if product:
            if cost_price is not None:
                product.cost_price = cost_price
            if mrp is not None:
                product.mrp = mrp
                product.sell_price = mrp
            product.updated_at = datetime.utcnow()

        self.session.flush()
        return inv

    def decrement_stock_atomic(self, product_id: int, quantity: Decimal) -> bool:
        """
        Atomically decrements stock ensuring quantity >= :quantity.
        Returns True if successful, False if insufficient stock.
        """
        # We execute direct atomic update with condition
        stmt = (
            self.session.query(Inventory)
            .filter(Inventory.product_id == product_id, Inventory.quantity >= quantity)
            .update(
                {
                    Inventory.quantity: Inventory.quantity - quantity,
                    Inventory.updated_at: datetime.utcnow(),
                },
                synchronize_session=False,
            )
        )
        self.session.flush()
        return stmt > 0

    def get_low_stock(self) -> List[Dict[str, Any]]:
        """Fetch items where stock <= reorder_level."""
        results = (
            self.session.query(Product, Inventory.quantity)
            .join(Inventory, Product.id == Inventory.product_id)
            .filter(Inventory.quantity <= Product.reorder_level)
            .order_by(Inventory.quantity.asc())
            .all()
        )
        return [
            {
                "product_id": p.id,
                "name": p.name,
                "unit": p.unit,
                "current_stock": float(qty),
                "reorder_level": float(p.reorder_level),
            }
            for p, qty in results
        ]


# --- Billing Repository ---

class BillingRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_draft_by_chat(self, chat_id: int) -> Optional[Bill]:
        return (
            self.session.query(Bill)
            .filter(Bill.telegram_chat_id == chat_id, Bill.status == "DRAFT")
            .order_by(Bill.id.desc())
            .first()
        )

    def get_by_id(self, bill_id: int) -> Optional[Bill]:
        return self.session.query(Bill).filter(Bill.id == bill_id).first()

    def get_by_bill_number(self, bill_number: str) -> Optional[Bill]:
        return self.session.query(Bill).filter(Bill.bill_number == bill_number).first()

    def create_draft(self, chat_id: int, payment_mode: str = "UPI", customer_id: Optional[int] = None) -> Bill:
        # Cancel any prior open draft for this chat
        prior_drafts = (
            self.session.query(Bill)
            .filter(Bill.telegram_chat_id == chat_id, Bill.status == "DRAFT")
            .all()
        )
        for d in prior_drafts:
            d.status = "CANCELLED"
            d.finalized_at = datetime.utcnow()

        import uuid
        today_str = datetime.utcnow().strftime("%Y%m%d")
        count = self.session.query(func.count(Bill.id)).filter(Bill.bill_number.like(f"INV-{today_str}-%")).scalar() or 0
        bill_number = f"INV-{today_str}-{count + 1:04d}-{uuid.uuid4().hex[:4].upper()}"

        bill = Bill(
            bill_number=bill_number,
            telegram_chat_id=chat_id,
            status="DRAFT",
            payment_mode=payment_mode,
            customer_id=customer_id,
            subtotal=Decimal("0.00"),
            cgst=Decimal("0.00"),
            sgst=Decimal("0.00"),
            total_tax=Decimal("0.00"),
            grand_total=Decimal("0.00"),
        )
        self.session.add(bill)
        self.session.flush()
        return bill

    def recalculate_bill_totals(self, bill: Bill):
        subtotal = Decimal("0.00")
        cgst = Decimal("0.00")
        sgst = Decimal("0.00")
        total_tax = Decimal("0.00")
        grand_total = Decimal("0.00")

        for item in bill.items:
            subtotal += item.taxable_amount
            cgst += item.cgst
            sgst += item.sgst
            grand_total += item.total

        total_tax = cgst + sgst
        bill.subtotal = round_money(subtotal)
        bill.cgst = round_money(cgst)
        bill.sgst = round_money(sgst)
        bill.total_tax = round_money(total_tax)
        bill.grand_total = round_money(grand_total)
        self.session.flush()

    def add_or_update_item(
        self,
        bill_id: int,
        product_id: int,
        quantity: Decimal,
        unit_price: Optional[Decimal] = None,
        replace_quantity: bool = False,
    ) -> BillItem:
        bill = self.session.query(Bill).filter(Bill.id == bill_id).first()
        if not bill or bill.status != "DRAFT":
            raise ValueError("Draft bill not found or already finalized.")

        product = self.session.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise ValueError(f"Product ID {product_id} not found.")

        price = unit_price if unit_price is not None else product.sell_price
        if price < product.cost_price:
            raise BelowCostPriceError(product.name, price, product.cost_price)

        item = (
            self.session.query(BillItem)
            .filter(BillItem.bill_id == bill_id, BillItem.product_id == product_id)
            .first()
        )

        final_qty = quantity if (replace_quantity or not item) else (item.quantity + quantity)
        if final_qty <= 0:
            if item:
                self.session.delete(item)
                self.session.flush()
                self.recalculate_bill_totals(bill)
            return None

        taxable, cgst, sgst, total = calculate_item_taxes(price, final_qty, product.gst_rate)

        if not item:
            item = BillItem(
                bill_id=bill_id,
                product_id=product_id,
                quantity=final_qty,
                unit_price=price,
                gst_rate=product.gst_rate,
                taxable_amount=taxable,
                cgst=cgst,
                sgst=sgst,
                total=total,
            )
            self.session.add(item)
        else:
            item.quantity = final_qty
            item.unit_price = price
            item.gst_rate = product.gst_rate
            item.taxable_amount = taxable
            item.cgst = cgst
            item.sgst = sgst
            item.total = total

        self.session.flush()
        self.recalculate_bill_totals(bill)
        return item

    def remove_item(self, bill_id: int, product_id: int) -> bool:
        bill = self.session.query(Bill).filter(Bill.id == bill_id).first()
        if not bill or bill.status != "DRAFT":
            return False

        item = (
            self.session.query(BillItem)
            .filter(BillItem.bill_id == bill_id, BillItem.product_id == product_id)
            .first()
        )
        if item:
            self.session.delete(item)
            self.session.flush()
            self.recalculate_bill_totals(bill)
            return True
        return False


# --- Khata Repository ---

class KhataRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_or_create_customer(self, name: str, phone: Optional[str] = None) -> Customer:
        term = name.strip()
        customer = self.session.query(Customer).filter(Customer.name.ilike(term)).first()
        if not customer:
            customer = Customer(name=term, phone=phone.strip() if phone else None)
            self.session.add(customer)
            self.session.flush()
        elif phone and not customer.phone:
            customer.phone = phone.strip()
            self.session.flush()
        return customer

    def find_customers(self, query: str) -> List[Customer]:
        term = f"%{query.strip()}%"
        return (
            self.session.query(Customer)
            .filter(or_(Customer.name.ilike(term), Customer.phone.ilike(term)))
            .all()
        )

    def add_transaction(
        self,
        customer_id: int,
        transaction_type: str,
        amount: Decimal,
        reference: Optional[str] = None,
    ) -> KhataTransaction:
        if amount <= 0:
            raise ValueError("Transaction amount must be positive.")
        if transaction_type not in ("CREDIT", "PAYMENT"):
            raise ValueError(f"Invalid transaction type '{transaction_type}'. Must be 'CREDIT' or 'PAYMENT'.")

        tx = KhataTransaction(
            customer_id=customer_id,
            transaction_type=transaction_type,
            amount=round_money(amount),
            reference=reference,
        )
        self.session.add(tx)
        self.session.flush()
        return tx

    def get_balance(self, customer_id: int) -> Decimal:
        """
        Balance = Total CREDIT (goods given to customer on debt) - Total PAYMENT (money repaid by customer).
        Positive balance means customer owes money to shop.
        """
        credits = (
            self.session.query(func.coalesce(func.sum(KhataTransaction.amount), Decimal("0.00")))
            .filter(KhataTransaction.customer_id == customer_id, KhataTransaction.transaction_type == "CREDIT")
            .scalar()
        )
        payments = (
            self.session.query(func.coalesce(func.sum(KhataTransaction.amount), Decimal("0.00")))
            .filter(KhataTransaction.customer_id == customer_id, KhataTransaction.transaction_type == "PAYMENT")
            .scalar()
        )
        return round_money(credits - payments)


# --- Owner Preferences Repository ---

class PreferenceRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        pref = self.session.query(OwnerPreference).filter(OwnerPreference.key == key.strip().lower()).first()
        return pref.value if pref else default

    def set(self, key: str, value: str) -> OwnerPreference:
        k = key.strip().lower()
        pref = self.session.query(OwnerPreference).filter(OwnerPreference.key == k).first()
        if not pref:
            pref = OwnerPreference(key=k, value=value.strip())
            self.session.add(pref)
        else:
            pref.value = value.strip()
            pref.updated_at = datetime.utcnow()
        self.session.flush()
        return pref


# --- Telegram Deduplication Repository ---

class TelegramUpdateRepository:
    def __init__(self, session: Session):
        self.session = session

    def is_already_processed(self, update_id: int) -> bool:
        rec = (
            self.session.query(ProcessedTelegramUpdate)
            .filter(ProcessedTelegramUpdate.telegram_update_id == update_id)
            .first()
        )
        return rec is not None

    def mark_processed(self, update_id: int) -> bool:
        if self.is_already_processed(update_id):
            return False
        rec = ProcessedTelegramUpdate(telegram_update_id=update_id)
        self.session.add(rec)
        self.session.flush()
        return True
