"""Seed realistic initial products, inventory, and preferences for Indian Kirana."""

import logging
from decimal import Decimal
from sqlalchemy.orm import Session
from app.database.models import Product, Inventory, Customer, OwnerPreference
from app.database.db import get_db

logger = logging.getLogger(__name__)

# NOTE: Demo/test GST and HSN values for Indian FMCG goods. Exact commercial classification is for demonstration.
SEED_PRODUCTS = [
    {
        "name": "Aashirvaad Atta 5kg",
        "sku": "AASH-ATTA-5KG",
        "brand": "ITC",
        "unit": "packet",
        "is_loose": False,
        "hsn_code": "1101",
        "gst_rate": Decimal("5.00"),
        "cost_price": Decimal("210.00"),
        "sell_price": Decimal("245.00"),
        "mrp": Decimal("245.00"),
        "reorder_level": Decimal("5.000"),
        "stock": Decimal("20.000"),
    },
    {
        "name": "Tata Salt 1kg",
        "sku": "TATA-SALT-1KG",
        "brand": "Tata",
        "unit": "packet",
        "is_loose": False,
        "hsn_code": "2501",
        "gst_rate": Decimal("0.00"),
        "cost_price": Decimal("22.00"),
        "sell_price": Decimal("28.00"),
        "mrp": Decimal("28.00"),
        "reorder_level": Decimal("10.000"),
        "stock": Decimal("4.000"),  # Low stock on purpose for testing
    },
    {
        "name": "Amul Butter 100g",
        "sku": "AMUL-BTR-100G",
        "brand": "Amul",
        "unit": "packet",
        "is_loose": False,
        "hsn_code": "0405",
        "gst_rate": Decimal("12.00"),
        "cost_price": Decimal("50.00"),
        "sell_price": Decimal("60.00"),
        "mrp": Decimal("60.00"),
        "reorder_level": Decimal("5.000"),
        "stock": Decimal("2.000"),  # Low stock on purpose
    },
    {
        "name": "Fortune Sunflower Oil 1L",
        "sku": "FORT-OIL-1L",
        "brand": "Fortune",
        "unit": "packet",
        "is_loose": False,
        "hsn_code": "1512",
        "gst_rate": Decimal("5.00"),
        "cost_price": Decimal("128.00"),
        "sell_price": Decimal("148.00"),
        "mrp": Decimal("148.00"),
        "reorder_level": Decimal("8.000"),
        "stock": Decimal("15.000"),
    },
    {
        "name": "Maggi 70g",
        "sku": "MAGGI-70G",
        "brand": "Nestle",
        "unit": "packet",
        "is_loose": False,
        "hsn_code": "1902",
        "gst_rate": Decimal("18.00"),
        "cost_price": Decimal("11.00"),
        "sell_price": Decimal("14.00"),
        "mrp": Decimal("14.00"),
        "reorder_level": Decimal("10.000"),
        "stock": Decimal("8.000"),  # Low stock on purpose
    },
    {
        "name": "Parle-G",
        "sku": "PARLE-G-GLUCOSE",
        "brand": "Parle",
        "unit": "packet",
        "is_loose": False,
        "hsn_code": "1905",
        "gst_rate": Decimal("18.00"),
        "cost_price": Decimal("8.00"),
        "sell_price": Decimal("10.00"),
        "mrp": Decimal("10.00"),
        "reorder_level": Decimal("15.000"),
        "stock": Decimal("50.000"),
    },
    {
        "name": "Surf Excel",
        "sku": "SURF-EXCEL-500G",
        "brand": "HUL",
        "unit": "packet",
        "is_loose": False,
        "hsn_code": "3402",
        "gst_rate": Decimal("18.00"),
        "cost_price": Decimal("105.00"),
        "sell_price": Decimal("130.00"),
        "mrp": Decimal("130.00"),
        "reorder_level": Decimal("5.000"),
        "stock": Decimal("12.000"),
    },
    {
        "name": "Loose Sugar",
        "sku": "LOOSE-SUGAR-KG",
        "brand": "Local",
        "unit": "kg",
        "is_loose": True,
        "hsn_code": "1701",
        "gst_rate": Decimal("5.00"),
        "cost_price": Decimal("38.00"),
        "sell_price": Decimal("44.00"),
        "mrp": Decimal("44.00"),
        "reorder_level": Decimal("10.000"),
        "stock": Decimal("18.500"),
    },
    {
        "name": "Loose Rice",
        "sku": "LOOSE-RICE-KG",
        "brand": "Local",
        "unit": "kg",
        "is_loose": True,
        "hsn_code": "1006",
        "gst_rate": Decimal("0.00"),
        "cost_price": Decimal("46.00"),
        "sell_price": Decimal("55.00"),
        "mrp": Decimal("55.00"),
        "reorder_level": Decimal("20.000"),
        "stock": Decimal("65.000"),
    },
    {
        "name": "Loose Dal",
        "sku": "LOOSE-TOOR-DAL-KG",
        "brand": "Local",
        "unit": "kg",
        "is_loose": True,
        "hsn_code": "0713",
        "gst_rate": Decimal("0.00"),
        "cost_price": Decimal("120.00"),
        "sell_price": Decimal("140.00"),
        "mrp": Decimal("140.00"),
        "reorder_level": Decimal("15.000"),
        "stock": Decimal("30.000"),
    },
]


def seed_database(db: Session):
    """Seed products, inventory, customers and default preferences."""
    logger.info("Seeding supermarket database...")

    # 1. Products and inventory
    for item_data in SEED_PRODUCTS:
        existing = db.query(Product).filter(Product.sku == item_data["sku"]).first()
        if not existing:
            p = Product(
                name=item_data["name"],
                sku=item_data["sku"],
                brand=item_data["brand"],
                unit=item_data["unit"],
                is_loose=item_data["is_loose"],
                hsn_code=item_data["hsn_code"],
                gst_rate=item_data["gst_rate"],
                cost_price=item_data["cost_price"],
                sell_price=item_data["sell_price"],
                mrp=item_data["mrp"],
                reorder_level=item_data["reorder_level"],
            )
            db.add(p)
            db.flush()

            inv = Inventory(
                product_id=p.id,
                quantity=item_data["stock"],
            )
            db.add(inv)
        else:
            # Update stock if inventory entry missing
            inv = db.query(Inventory).filter(Inventory.product_id == existing.id).first()
            if not inv:
                inv = Inventory(product_id=existing.id, quantity=item_data["stock"])
                db.add(inv)

    # 2. Sample Customers
    sample_customers = [
        {"name": "Ramesh", "phone": "9876543210"},
        {"name": "Suresh", "phone": "9876543211"},
        {"name": "Priya", "phone": "9876543212"},
    ]
    for c_data in sample_customers:
        c = db.query(Customer).filter(Customer.name == c_data["name"]).first()
        if not c:
            db.add(Customer(name=c_data["name"], phone=c_data["phone"]))

    # 3. Default Shop Preferences
    default_preferences = {
        "shop_name": "Sri Lakshmi Stores",
        "gstin": "33AAAAA0000A1Z5",
        "default_payment": "UPI",
        "address": "12 Bazaar Street, Anna Nagar, Chennai, Tamil Nadu - 600040",
        "phone": "+91 98765 43210",
    }
    for k, v in default_preferences.items():
        pref = db.query(OwnerPreference).filter(OwnerPreference.key == k).first()
        if not pref:
            db.add(OwnerPreference(key=k, value=v))

    db.commit()
    logger.info("Database seeding completed successfully.")


if __name__ == "__main__":
    from app.database.db import init_db
    init_db()
    with get_db() as session:
        seed_database(session)
    print("Seed complete.")
