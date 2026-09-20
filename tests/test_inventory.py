"""Tests for inventory operations: product creation, stock receiving, stock queries, and low-stock detection."""

import pytest
from decimal import Decimal
from app.services.inventory_service import InventoryService
from app.database.models import Product, Inventory


def test_01_product_creation(db_session):
    """Requirement 1: Product creation with pricing, GST rate, and initial stock."""
    service = InventoryService(db_session)
    product_data = service.add_product(
        name="Britannia Good Day 100g",
        mrp=30.0,
        cost_price=24.0,
        sell_price=30.0,
        gst_rate=18.0,
        unit="packet",
        brand="Britannia",
        is_loose=False,
        hsn_code="1905",
        reorder_level=12.0,
        initial_stock=25.0,
    )

    assert product_data["name"] == "Britannia Good Day 100g"
    assert product_data["mrp"] == 30.0
    assert product_data["cost_price"] == 24.0
    assert product_data["sell_price"] == 30.0
    assert product_data["gst_rate"] == 18.0
    assert product_data["current_stock"] == 25.0

    # Verify persisted in database
    p = db_session.query(Product).filter(Product.id == product_data["id"]).first()
    assert p is not None
    assert p.sku.startswith("BRITANNIA-GOOD-DAY-")
    assert p.inventory.quantity == Decimal("25.000")


def test_02_stock_receiving(seeded_session):
    """Requirement 2: Stock receiving updates quantity, cost price, and MRP correctly."""
    service = InventoryService(seeded_session)
    # Maggi 70g starts with 8 packets in seed data
    maggi = seeded_session.query(Product).filter(Product.name == "Maggi 70g").first()
    assert maggi is not None
    initial_stock = maggi.inventory.quantity

    result = service.receive_stock(
        product_id=maggi.id,
        quantity=50.0,
        cost_price=12.0,
        mrp=15.0,
    )

    assert result["added_quantity"] == 50.0
    assert result["new_stock"] == float(initial_stock) + 50.0
    assert result["cost_price"] == 12.0
    assert result["mrp"] == 15.0

    # Ensure DB record reflects new quantity and updated pricing
    seeded_session.refresh(maggi)
    assert maggi.inventory.quantity == initial_stock + Decimal("50.000")
    assert maggi.cost_price == Decimal("12.00")
    assert maggi.mrp == Decimal("15.00")


def test_03_stock_query(seeded_session):
    """Requirement 3: Stock query by ID and fuzzy product name."""
    service = InventoryService(seeded_session)
    
    # Query by ID
    sugar = seeded_session.query(Product).filter(Product.name == "Loose Sugar").first()
    res_id = service.get_stock(product_id=sugar.id)
    assert res_id["found"] is True
    assert res_id["name"] == "Loose Sugar"
    assert res_id["stock"] == 18.5
    assert res_id["unit"] == "kg"

    # Query by query text
    res_query = service.get_stock(query="Sugar")
    assert res_query["found"] is True
    assert res_query["name"] == "Loose Sugar"
    assert res_query["stock"] == 18.5

    # Non-existent product query
    res_missing = service.get_stock(query="NonExistentItemXYZ")
    assert res_missing["found"] is False


def test_04_low_stock_detection(seeded_session):
    """Requirement 4: Low-stock detection identifies all products at or below reorder level."""
    service = InventoryService(seeded_session)
    low_stock = service.get_low_stock()

    assert len(low_stock) > 0
    names = [item["name"] for item in low_stock]
    
    # Seed data intentionally sets Tata Salt, Amul Butter, Maggi below reorder
    assert "Tata Salt 1kg" in names
    assert "Amul Butter 100g" in names
    assert "Maggi 70g" in names

    for item in low_stock:
        assert item["current_stock"] <= item["reorder_level"]
