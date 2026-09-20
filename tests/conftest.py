"""Shared fixtures and in-memory test database setup."""

import pytest
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.db import Base
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
from app.seed.seed_data import seed_database


@pytest.fixture(scope="function")
def db_engine():
    """Create fresh in-memory SQLite database for testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session(db_engine):
    """Yield an isolated database session with rollback/close."""
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
        bind=db_engine,
    )
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def seeded_session(db_session):
    """Yield a database session pre-populated with standard realistic seed data."""
    seed_database(db_session)
    return db_session
