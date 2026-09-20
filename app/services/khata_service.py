"""Khata ledger service for managing customer credit, debt, and repayments."""

from decimal import Decimal
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.database.repositories import KhataRepository
from app.database.models import Customer


class KhataService:
    def __init__(self, session: Session):
        self.session = session
        self.khata_repo = KhataRepository(session)

    def find_customers(self, query: str) -> List[Dict[str, Any]]:
        """Find customers matching query name or phone."""
        customers = self.khata_repo.find_customers(query)
        result = []
        for c in customers:
            balance = self.khata_repo.get_balance(c.id)
            d = c.to_dict()
            d["balance"] = float(balance)
            result.append(d)
        return result

    def get_or_create_customer(self, name: str, phone: Optional[str] = None) -> Dict[str, Any]:
        """Fetch or create customer by name."""
        cust = self.khata_repo.get_or_create_customer(name=name, phone=phone)
        self.session.commit()
        balance = self.khata_repo.get_balance(cust.id)
        d = cust.to_dict()
        d["balance"] = float(balance)
        return d

    def add_credit(self, customer_name_or_id: str, amount: float, reference: Optional[str] = None) -> Dict[str, Any]:
        """
        Record goods given on credit to customer (Customer owes money).
        Increases customer outstanding balance.
        """
        if amount <= 0:
            raise ValueError("Credit amount must be positive.")

        cust = self._resolve_customer(customer_name_or_id)
        tx = self.khata_repo.add_transaction(
            customer_id=cust.id,
            transaction_type="CREDIT",
            amount=Decimal(str(amount)),
            reference=reference or "Manual credit entry",
        )
        self.session.commit()
        new_balance = self.khata_repo.get_balance(cust.id)
        return {
            "customer_id": cust.id,
            "customer_name": cust.name,
            "transaction_type": "CREDIT",
            "amount": float(tx.amount),
            "reference": tx.reference,
            "new_balance": float(new_balance),
        }

    def record_payment(self, customer_name_or_id: str, amount: float, reference: Optional[str] = None) -> Dict[str, Any]:
        """
        Record repayment made by customer.
        Decreases customer outstanding balance.
        """
        if amount <= 0:
            raise ValueError("Payment amount must be positive.")

        cust = self._resolve_customer(customer_name_or_id)
        tx = self.khata_repo.add_transaction(
            customer_id=cust.id,
            transaction_type="PAYMENT",
            amount=Decimal(str(amount)),
            reference=reference or "Cash/UPI repayment",
        )
        self.session.commit()
        new_balance = self.khata_repo.get_balance(cust.id)
        return {
            "customer_id": cust.id,
            "customer_name": cust.name,
            "transaction_type": "PAYMENT",
            "amount": float(tx.amount),
            "reference": tx.reference,
            "new_balance": float(new_balance),
        }

    def get_balance(self, customer_name_or_id: str) -> Dict[str, Any]:
        """Get the current outstanding ledger balance for a customer."""
        cust = self._resolve_customer(customer_name_or_id)
        balance = self.khata_repo.get_balance(cust.id)
        return {
            "customer_id": cust.id,
            "customer_name": cust.name,
            "balance": float(balance),
            "status": "OWES_SHOP" if balance > 0 else ("ADVANCE_PAYMENT" if balance < 0 else "SETTLED"),
        }

    def _resolve_customer(self, customer_name_or_id: str) -> Customer:
        if str(customer_name_or_id).isdigit():
            c = self.session.query(Customer).filter(Customer.id == int(customer_name_or_id)).first()
            if c:
                return c

        matches = self.khata_repo.find_customers(str(customer_name_or_id))
        if len(matches) == 1:
            return matches[0]
        elif len(matches) > 1:
            # Exact match check
            for m in matches:
                if m.name.lower() == str(customer_name_or_id).lower():
                    return m
            return matches[0]
        else:
            # Auto-create customer
            return self.khata_repo.get_or_create_customer(name=str(customer_name_or_id))
