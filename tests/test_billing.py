"""Tests for billing workflows, multi-turn drafts, GST calculations, oversell rejection, and guardrails."""

import pytest
from decimal import Decimal
from app.services.billing_service import BillingService
from app.services.inventory_service import InventoryService
from app.database.models import Product, Bill, Inventory
from app.database.repositories import InsufficientStockError, BelowCostPriceError


def test_05_basic_billing(seeded_session):
    """Requirement 5: Basic billing creates draft, calculates totals, and finalizes with stock decrement."""
    b_svc = BillingService(seeded_session)
    i_svc = InventoryService(seeded_session)

    sugar = seeded_session.query(Product).filter(Product.name == "Loose Sugar").first()
    initial_stock = i_svc.get_stock(sugar.id)["stock"]

    chat_id = 1001
    draft = b_svc.get_or_create_draft(chat_id=chat_id, payment_mode="UPI")
    assert draft["status"] == "DRAFT"

    # Add 2kg sugar @ ₹44/kg
    b_svc.add_item(chat_id=chat_id, product_id=sugar.id, quantity=2.0)

    # In draft mode, stock must NOT have changed yet!
    assert i_svc.get_stock(sugar.id)["stock"] == initial_stock

    # Finalize bill
    fin = b_svc.finalize_bill(chat_id=chat_id)
    assert fin["bill"]["status"] == "FINALIZED"
    assert fin["bill"]["grand_total"] == 88.0

    # After finalization, stock must be decremented
    new_stock = i_svc.get_stock(sugar.id)["stock"]
    assert new_stock == initial_stock - 2.0


def test_06_multi_turn_billing(seeded_session):
    """Requirement 6: Multi-turn draft bill preserves state across simulated turns."""
    b_svc = BillingService(seeded_session)
    chat_id = 1002

    sugar = seeded_session.query(Product).filter(Product.name == "Loose Sugar").first()
    atta = seeded_session.query(Product).filter(Product.name == "Aashirvaad Atta 5kg").first()
    maggi = seeded_session.query(Product).filter(Product.name == "Maggi 70g").first()

    # Turn 1: Add sugar
    b_svc.add_item(chat_id=chat_id, product_id=sugar.id, quantity=2.0)
    bill1 = b_svc.get_current_bill(chat_id)
    assert len(bill1["items"]) == 1

    # Turn 2: Add atta
    b_svc.add_item(chat_id=chat_id, product_id=atta.id, quantity=1.0)
    bill2 = b_svc.get_current_bill(chat_id)
    assert len(bill2["items"]) == 2

    # Turn 3: Add 4 Maggi
    b_svc.add_item(chat_id=chat_id, product_id=maggi.id, quantity=4.0)
    bill3 = b_svc.get_current_bill(chat_id)
    assert len(bill3["items"]) == 3

    # All items correctly accumulated in the same draft
    product_names = [it["product_name"] for it in bill3["items"]]
    assert "Loose Sugar" in product_names
    assert "Aashirvaad Atta 5kg" in product_names
    assert "Maggi 70g" in product_names


def test_07_bill_editing(seeded_session):
    """Requirement 7: Bill editing: drop item and modify item quantity."""
    b_svc = BillingService(seeded_session)
    chat_id = 1003

    maggi = seeded_session.query(Product).filter(Product.name == "Maggi 70g").first()
    butter = seeded_session.query(Product).filter(Product.name == "Amul Butter 100g").first()

    b_svc.add_item(chat_id=chat_id, product_id=maggi.id, quantity=4.0)
    b_svc.add_item(chat_id=chat_id, product_id=butter.id, quantity=1.0)

    bill = b_svc.get_current_bill(chat_id)
    assert len(bill["items"]) == 2

    # User: "drop the butter, make it 6 Maggi"
    b_svc.remove_item(chat_id=chat_id, product_id=butter.id)
    b_svc.update_item(chat_id=chat_id, product_id=maggi.id, quantity=6.0)

    updated_bill = b_svc.get_current_bill(chat_id)
    assert len(updated_bill["items"]) == 1
    assert updated_bill["items"][0]["product_name"] == "Maggi 70g"
    assert updated_bill["items"][0]["quantity"] == 6.0
    # 6 Maggi @ 14 = 84.0
    assert updated_bill["grand_total"] == 84.0


def test_08_gst_calculation(seeded_session):
    """Requirement 8: GST intra-state split (CGST + SGST) calculated with exact Decimal precision."""
    b_svc = BillingService(seeded_session)
    chat_id = 1004

    # Maggi has 18% GST, MRP ₹14
    # For 1 packet: total = 14.00, taxable = 14 / 1.18 = 11.8644 -> 11.86
    # total tax = 14.00 - 11.86 = 2.14
    # cgst = 1.07, sgst = 1.07
    maggi = seeded_session.query(Product).filter(Product.name == "Maggi 70g").first()
    b_svc.add_item(chat_id=chat_id, product_id=maggi.id, quantity=1.0)

    bill = b_svc.get_current_bill(chat_id)
    item = bill["items"][0]
    assert item["total"] == 14.00
    assert item["taxable_amount"] == 11.86
    assert item["cgst"] == 1.07
    assert item["sgst"] == 1.07
    assert round(item["cgst"] + item["sgst"], 2) == round(item["total"] - item["taxable_amount"], 2)
    assert bill["total_tax"] == 2.14
    assert bill["grand_total"] == 14.00


def test_09_oversell_rejection(seeded_session):
    """Requirement 9: Oversell rejection: Backend rejects billing when stock is insufficient."""
    b_svc = BillingService(seeded_session)
    i_svc = InventoryService(seeded_session)
    chat_id = 1005

    # Maggi starts with 8 packets in seed data
    maggi = seeded_session.query(Product).filter(Product.name == "Maggi 70g").first()
    available_stock = i_svc.get_stock(maggi.id)["stock"]

    # User attempts to bill 10 Maggi (stock is only 8)
    b_svc.add_item(chat_id=chat_id, product_id=maggi.id, quantity=10.0)

    # Attempting to finalize MUST raise InsufficientStockError and leave stock unchanged
    with pytest.raises(InsufficientStockError) as exc_info:
        b_svc.finalize_bill(chat_id=chat_id)

    assert "Insufficient stock" in str(exc_info.value)
    assert exc_info.value.available == Decimal(str(available_stock))
    assert exc_info.value.requested == Decimal("10.0")

    # Inventory must remain completely intact
    assert i_svc.get_stock(maggi.id)["stock"] == available_stock


def test_10_selling_below_cost(seeded_session):
    """Requirement 10: Selling below cost is rejected by backend validation."""
    b_svc = BillingService(seeded_session)
    chat_id = 1006

    # Maggi cost_price is ₹11.00
    maggi = seeded_session.query(Product).filter(Product.name == "Maggi 70g").first()

    # Attempt to add Maggi with custom price of ₹9.00 (below cost of ₹11)
    with pytest.raises(BelowCostPriceError) as exc_info:
        b_svc.add_item(chat_id=chat_id, product_id=maggi.id, quantity=1.0, unit_price=9.0)

    assert "below cost price" in str(exc_info.value)
