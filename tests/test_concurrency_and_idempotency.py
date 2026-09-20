"""Tests for concurrency, idempotency, persistence across restarts, and Telegram update deduplication."""

import os
import tempfile
import threading
from decimal import Decimal
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.db import Base
from app.database.models import Product, Inventory, Bill, OwnerPreference, ProcessedTelegramUpdate
from app.services.billing_service import BillingService
from app.services.inventory_service import InventoryService
from app.services.preference_service import PreferenceService
from app.database.repositories import TelegramUpdateRepository, InsufficientStockError
from app.seed.seed_data import seed_database


def test_16_idempotent_finalization(seeded_session):
    """Requirement 16: Finalize operation with idempotency key is idempotent and has no duplicate side effects."""
    b_svc = BillingService(seeded_session)
    i_svc = InventoryService(seeded_session)
    chat_id = 1009

    maggi = seeded_session.query(Product).filter(Product.name == "Maggi 70g").first()
    stock_before = i_svc.get_stock(maggi.id)["stock"]

    b_svc.get_or_create_draft(chat_id=chat_id)
    b_svc.add_item(chat_id=chat_id, product_id=maggi.id, quantity=2.0)

    idempotency_key = "IDEMP-REQ-12345"

    # First finalization
    res1 = b_svc.finalize_bill(chat_id=chat_id, idempotency_key=idempotency_key)
    assert res1["already_finalized"] is False
    assert res1["bill"]["status"] == "FINALIZED"
    stock_after_first = i_svc.get_stock(maggi.id)["stock"]
    assert stock_after_first == stock_before - 2.0

    # Duplicate finalization request with the same idempotency key
    res2 = b_svc.finalize_bill(chat_id=chat_id, idempotency_key=idempotency_key)
    assert res2["already_finalized"] is True
    assert res2["bill"]["bill_number"] == res1["bill"]["bill_number"]

    # Stock must NOT have decremented a second time!
    stock_after_second = i_svc.get_stock(maggi.id)["stock"]
    assert stock_after_second == stock_after_first


def test_17_concurrent_stock_deduction():
    """
    Requirement 17: Concurrent stock deduction:
    Bill A selling 4 Maggi and Bill B selling 3 Maggi when only 6 exist.
    One transaction succeeds, the second is rejected, stock remains non-negative.
    """
    # Create a shared file-backed SQLite database with WAL mode for concurrency testing
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_concurrent.db")
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    # Setup 6 Maggi in stock
    setup_session = Session()
    p = Product(
        name="Maggi 70g Concurrency",
        sku="MAGGI-CONCUR-70G",
        unit="packet",
        cost_price=Decimal("11.00"),
        sell_price=Decimal("14.00"),
        mrp=Decimal("14.00"),
        gst_rate=Decimal("18.00"),
        reorder_level=Decimal("5.000"),
    )
    setup_session.add(p)
    setup_session.flush()
    inv = Inventory(product_id=p.id, quantity=Decimal("6.000"))
    setup_session.add(inv)
    setup_session.commit()
    prod_id = p.id
    setup_session.close()

    results = []
    errors = []

    def process_bill(chat_id: int, qty: float):
        session = Session()
        try:
            b_svc = BillingService(session)
            b_svc.get_or_create_draft(chat_id=chat_id)
            b_svc.add_item(chat_id=chat_id, product_id=prod_id, quantity=qty)
            fin = b_svc.finalize_bill(chat_id=chat_id)
            results.append((chat_id, fin))
        except InsufficientStockError as e:
            errors.append((chat_id, str(e)))
        finally:
            session.close()

    # Thread 1 tries to bill 4 Maggi, Thread 2 tries to bill 3 Maggi
    t1 = threading.Thread(target=process_bill, args=(2001, 4.0))
    t2 = threading.Thread(target=process_bill, args=(2002, 3.0))

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Verify: One must succeed and one must fail
    assert len(results) == 1, f"Expected exactly 1 success, got {len(results)}"
    assert len(errors) == 1, f"Expected exactly 1 failure, got {len(errors)}"

    # Final stock check
    verify_session = Session()
    final_stock = verify_session.query(Inventory).filter(Inventory.product_id == prod_id).first().quantity
    verify_session.close()

    # If t1 won, 6 - 4 = 2. If t2 won, 6 - 3 = 3. Stock is strictly >= 0.
    assert final_stock in (Decimal("2.000"), Decimal("3.000"))
    assert final_stock >= Decimal("0.000")


def test_18_persistence_after_restart():
    """Requirement 18: Persistence after restart: Database data survives engine close and reconnect."""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_restart.db")

    # Session 1: Create and commit data
    engine1 = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(bind=engine1)
    Session1 = sessionmaker(bind=engine1)
    s1 = Session1()
    seed_database(s1)
    p_name = "Aashirvaad Atta 5kg"
    atta = s1.query(Product).filter(Product.name == p_name).first()
    assert atta is not None
    s1.close()
    engine1.dispose()  # Simulate complete application restart

    # Session 2: Connect afresh and verify data remains intact
    engine2 = create_engine(f"sqlite:///{db_path}")
    Session2 = sessionmaker(bind=engine2)
    s2 = Session2()
    reopened_atta = s2.query(Product).filter(Product.name == p_name).first()
    assert reopened_atta is not None
    assert reopened_atta.inventory.quantity == Decimal("20.000")
    s2.close()
    engine2.dispose()


def test_19_preference_persistence(seeded_session):
    """Requirement 19: Stored owner preferences persist reliably."""
    pref_svc = PreferenceService(seeded_session)

    # Set custom preference
    pref_svc.set_preference("default_payment", "CASH")
    pref_svc.set_preference("default_atta", "Aashirvaad 5kg")

    # Read back
    assert pref_svc.get_preference("default_payment") == "CASH"
    assert pref_svc.get_preference("default_atta") == "Aashirvaad 5kg"

    # Verify in DB table directly
    rec = seeded_session.query(OwnerPreference).filter(OwnerPreference.key == "default_atta").first()
    assert rec is not None
    assert rec.value == "Aashirvaad 5kg"


def test_20_duplicate_telegram_update_handling(seeded_session):
    """Requirement 20: Duplicate Telegram updates are deduplicated and not processed twice."""
    repo = TelegramUpdateRepository(seeded_session)
    update_id = 987654321

    # First delivery
    assert repo.is_already_processed(update_id) is False
    assert repo.mark_processed(update_id) is True

    # Immediate check
    assert repo.is_already_processed(update_id) is True

    # Redelivered duplicate from Telegram
    assert repo.mark_processed(update_id) is False
