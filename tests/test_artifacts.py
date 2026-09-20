"""Tests for artifact generation: ReportLab PDF invoices and python-pptx PowerPoint analysis decks."""

import os
import pytest
from app.services.billing_service import BillingService
from app.artifacts.invoice_pdf import generate_invoice_pdf
from app.artifacts.analytics_deck import generate_analysis_pptx
from app.database.models import Product


def test_14_pdf_generation(seeded_session):
    """Requirement 14: PDF invoice generator produces a valid, readable PDF document."""
    b_svc = BillingService(seeded_session)
    chat_id = 1007

    maggi = seeded_session.query(Product).filter(Product.name == "Maggi 70g").first()
    sugar = seeded_session.query(Product).filter(Product.name == "Loose Sugar").first()

    b_svc.get_or_create_draft(chat_id=chat_id, payment_mode="UPI", customer_name="Ramesh")
    b_svc.add_item(chat_id=chat_id, product_id=maggi.id, quantity=4.0)
    b_svc.add_item(chat_id=chat_id, product_id=sugar.id, quantity=2.0)
    fin = b_svc.finalize_bill(chat_id=chat_id)

    pdf_path = generate_invoice_pdf(bill_id=fin["bill"]["id"], session=seeded_session)

    assert os.path.exists(pdf_path)
    assert pdf_path.endswith(".pdf")
    assert os.path.getsize(pdf_path) > 1000  # Non-trivial PDF file size


def test_15_pptx_generation(seeded_session):
    """Requirement 15: PowerPoint analysis deck generator creates presentation with real DB data and slides."""
    # Seed a finalized bill to ensure non-empty analytics
    b_svc = BillingService(seeded_session)
    maggi = seeded_session.query(Product).filter(Product.name == "Maggi 70g").first()
    b_svc.get_or_create_draft(chat_id=1008, payment_mode="CASH")
    b_svc.add_item(chat_id=1008, product_id=maggi.id, quantity=2.0)
    b_svc.finalize_bill(chat_id=1008)

    pptx_path = generate_analysis_pptx(period="week", session=seeded_session)

    assert os.path.exists(pptx_path)
    assert pptx_path.endswith(".pptx")
    assert os.path.getsize(pptx_path) > 5000  # Non-trivial PPTX file with embedded charts
