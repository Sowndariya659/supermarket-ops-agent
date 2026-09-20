"""Tests for customer credit ledger, repayment records, and balance calculations."""

import pytest
from app.services.khata_service import KhataService
from app.database.models import Customer, KhataTransaction


def test_11_khata_credit(seeded_session):
    """Requirement 11: Adding credit records a CREDIT ledger transaction and updates balance."""
    k_svc = KhataService(seeded_session)

    # Ramesh gets ₹500 on credit
    res = k_svc.add_credit(customer_name_or_id="Ramesh", amount=500.0, reference="Groceries on credit")

    assert res["customer_name"] == "Ramesh"
    assert res["transaction_type"] == "CREDIT"
    assert res["amount"] == 500.0
    assert res["new_balance"] == 500.0

    # Ensure transaction was recorded in ledger
    txs = seeded_session.query(KhataTransaction).filter(KhataTransaction.customer_id == res["customer_id"]).all()
    assert len(txs) == 1
    assert txs[0].transaction_type == "CREDIT"


def test_12_khata_payment(seeded_session):
    """Requirement 12: Customer repayment records a PAYMENT ledger transaction and reduces debt."""
    k_svc = KhataService(seeded_session)

    # First credit ₹500
    k_svc.add_credit(customer_name_or_id="Ramesh", amount=500.0)

    # Ramesh pays ₹300
    res = k_svc.record_payment(customer_name_or_id="Ramesh", amount=300.0, reference="UPI payment")

    assert res["customer_name"] == "Ramesh"
    assert res["transaction_type"] == "PAYMENT"
    assert res["amount"] == 300.0
    assert res["new_balance"] == 200.0


def test_13_khata_balance_ledger_derived(seeded_session):
    """Requirement 13: Customer balance is derived dynamically from sum of ledger transactions."""
    k_svc = KhataService(seeded_session)

    # Sequence of transactions:
    # 1. Credit 500
    # 2. Payment 300 -> balance 200
    # 3. Credit 150 -> balance 350
    # 4. Payment 350 -> balance 0.0 (settled)
    k_svc.add_credit("Ramesh", 500.0)
    k_svc.record_payment("Ramesh", 300.0)
    k_svc.add_credit("Ramesh", 150.0)

    bal_res = k_svc.get_balance("Ramesh")
    assert bal_res["balance"] == 350.0
    assert bal_res["status"] == "OWES_SHOP"

    # Settle the remaining debt
    k_svc.record_payment("Ramesh", 350.0)
    settled_res = k_svc.get_balance("Ramesh")
    assert settled_res["balance"] == 0.0
    assert settled_res["status"] == "SETTLED"
