"""SQLAlchemy ORM models with strong constraints, Decimal types, and ledger integrity."""

from datetime import datetime
from decimal import Decimal
from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    String,
    Text,
    Boolean,
    Numeric,
    DateTime,
    ForeignKey,
    CheckConstraint,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import relationship
from app.database.db import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, index=True)
    sku = Column(String(64), unique=True, nullable=False, index=True)
    brand = Column(String(128), nullable=True)
    unit = Column(String(32), nullable=False, default="packet")  # kg, g, packet, L, ml, unit
    is_loose = Column(Boolean, nullable=False, default=False)
    hsn_code = Column(String(32), nullable=False, default="1904")
    gst_rate = Column(Numeric(5, 2), nullable=False, default=Decimal("5.00"))  # 0, 5, 12, 18, 28
    cost_price = Column(Numeric(12, 2), nullable=False)
    sell_price = Column(Numeric(12, 2), nullable=False)
    mrp = Column(Numeric(12, 2), nullable=False)
    reorder_level = Column(Numeric(12, 3), nullable=False, default=Decimal("10.000"))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    inventory = relationship("Inventory", back_populates="product", uselist=False, cascade="all, delete-orphan")
    bill_items = relationship("BillItem", back_populates="product")

    __table_args__ = (
        CheckConstraint("cost_price >= 0", name="chk_product_cost_positive"),
        CheckConstraint("sell_price >= 0", name="chk_product_sell_positive"),
        CheckConstraint("mrp >= 0", name="chk_product_mrp_positive"),
        CheckConstraint("gst_rate >= 0", name="chk_product_gst_positive"),
        CheckConstraint("reorder_level >= 0", name="chk_product_reorder_positive"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "sku": self.sku,
            "brand": self.brand,
            "unit": self.unit,
            "is_loose": self.is_loose,
            "hsn_code": self.hsn_code,
            "gst_rate": float(self.gst_rate),
            "cost_price": float(self.cost_price),
            "sell_price": float(self.sell_price),
            "mrp": float(self.mrp),
            "reorder_level": float(self.reorder_level),
            "current_stock": float(self.inventory.quantity) if self.inventory else 0.0,
        }


class Inventory(Base):
    __tablename__ = "inventory"

    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), primary_key=True)
    quantity = Column(Numeric(12, 3), nullable=False, default=Decimal("0.000"))
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    product = relationship("Product", back_populates="inventory")

    __table_args__ = (
        CheckConstraint("quantity >= 0", name="chk_inventory_non_negative"),
    )


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False, index=True)
    phone = Column(String(32), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    bills = relationship("Bill", back_populates="customer")
    khata_transactions = relationship("KhataTransaction", back_populates="customer", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "phone": self.phone,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Bill(Base):
    __tablename__ = "bills"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bill_number = Column(String(64), unique=True, nullable=False, index=True)
    telegram_chat_id = Column(BigInteger, nullable=False, index=True)
    status = Column(String(32), nullable=False, default="DRAFT", index=True)  # DRAFT, FINALIZED, CANCELLED
    subtotal = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    cgst = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    sgst = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    total_tax = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    grand_total = Column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    payment_mode = Column(String(32), nullable=False, default="UPI")  # UPI, CASH, KHATA, CARD
    payment_reference = Column(String(128), nullable=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    idempotency_key = Column(String(128), unique=True, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    finalized_at = Column(DateTime, nullable=True)

    # Relationships
    customer = relationship("Customer", back_populates="bills")
    items = relationship("BillItem", back_populates="bill", cascade="all, delete-orphan", order_by="BillItem.id")

    __table_args__ = (
        CheckConstraint("subtotal >= 0", name="chk_bill_subtotal_positive"),
        CheckConstraint("grand_total >= 0", name="chk_bill_grand_total_positive"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "bill_number": self.bill_number,
            "telegram_chat_id": self.telegram_chat_id,
            "status": self.status,
            "subtotal": float(self.subtotal),
            "cgst": float(self.cgst),
            "sgst": float(self.sgst),
            "total_tax": float(self.total_tax),
            "grand_total": float(self.grand_total),
            "payment_mode": self.payment_mode,
            "payment_reference": self.payment_reference,
            "customer_id": self.customer_id,
            "customer_name": self.customer.name if self.customer else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "finalized_at": self.finalized_at.isoformat() if self.finalized_at else None,
            "items": [item.to_dict() for item in self.items],
        }


class BillItem(Base):
    __tablename__ = "bill_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bill_id = Column(Integer, ForeignKey("bills.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    quantity = Column(Numeric(12, 3), nullable=False)
    unit_price = Column(Numeric(12, 2), nullable=False)
    gst_rate = Column(Numeric(5, 2), nullable=False)
    taxable_amount = Column(Numeric(12, 2), nullable=False)
    cgst = Column(Numeric(12, 2), nullable=False)
    sgst = Column(Numeric(12, 2), nullable=False)
    total = Column(Numeric(12, 2), nullable=False)

    bill = relationship("Bill", back_populates="items")
    product = relationship("Product", back_populates="bill_items")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="chk_bill_item_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="chk_bill_item_unit_price_positive"),
        UniqueConstraint("bill_id", "product_id", name="uq_bill_product"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "bill_id": self.bill_id,
            "product_id": self.product_id,
            "product_name": self.product.name if self.product else "Unknown",
            "unit": self.product.unit if self.product else "unit",
            "quantity": float(self.quantity),
            "unit_price": float(self.unit_price),
            "gst_rate": float(self.gst_rate),
            "taxable_amount": float(self.taxable_amount),
            "cgst": float(self.cgst),
            "sgst": float(self.sgst),
            "total": float(self.total),
        }


class KhataTransaction(Base):
    """
    Append-only customer ledger.
    CREDIT: Shop gave goods to customer on credit (Customer owes money -> Increases customer debit balance).
    PAYMENT: Customer paid money back (Decreases customer debit balance).
    """
    __tablename__ = "khata_transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    transaction_type = Column(String(32), nullable=False)  # CREDIT, PAYMENT
    amount = Column(Numeric(12, 2), nullable=False)
    reference = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    customer = relationship("Customer", back_populates="khata_transactions")

    __table_args__ = (
        CheckConstraint("amount > 0", name="chk_khata_amount_positive"),
        CheckConstraint("transaction_type IN ('CREDIT', 'PAYMENT')", name="chk_khata_tx_type"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "customer_id": self.customer_id,
            "customer_name": self.customer.name if self.customer else None,
            "transaction_type": self.transaction_type,
            "amount": float(self.amount),
            "reference": self.reference,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class OwnerPreference(Base):
    __tablename__ = "owner_preferences"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(128), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "key": self.key,
            "value": self.value,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ProcessedTelegramUpdate(Base):
    __tablename__ = "processed_telegram_updates"

    telegram_update_id = Column(BigInteger, primary_key=True)
    processed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
