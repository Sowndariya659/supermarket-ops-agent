"""Integration tests verifying the exact 10-step assignment demo flow through the Agent Orchestrator."""

import pytest
from app.agent.orchestrator import AgentOrchestrator
from app.database.models import Product, Inventory
from decimal import Decimal


def test_complete_10_step_demo_flow(seeded_session):
    """
    Validates Section 23 Demo Flow:
    1. Receive stock
    2. Create multi-item bill
    3. Edit the bill
    4. Attempt oversell
    5. Khata cycle
    6. Generate PDF invoice
    7. Generate PPTX analysis deck
    8. Set a preference
    9. Start /new chat
    10. Demonstrate preference is remembered
    """
    orchestrator = AgentOrchestrator()
    chat_id = 99999

    # Step 1: Receive stock
    # "50 packets of Maggi came in, cost ₹12, MRP ₹14"
    resp1 = orchestrator.process_message(
        chat_id=chat_id,
        user_text="50 packets of Maggi came in, cost ₹12, MRP ₹14",
        session=seeded_session,
    )
    assert "Received shipment" in resp1.text or "Added" in resp1.text
    assert "receive_stock" in resp1.tools_called

    # Step 2: Create multi-item bill
    # "make a bill: 2kg sugar, 1 Aashirvaad atta, 4 Maggi, 1 Amul butter, UPI"
    resp2 = orchestrator.process_message(
        chat_id=chat_id,
        user_text="make a bill: 2kg sugar, 1 Aashirvaad atta, 4 Maggi, 1 Amul butter, UPI",
        session=seeded_session,
    )
    assert "Draft Bill" in resp2.text or "created" in resp2.text
    assert "add_bill_item" in resp2.tools_called

    # Step 3: Edit the bill
    # "drop the butter, make it 6 Maggi"
    resp3 = orchestrator.process_message(
        chat_id=chat_id,
        user_text="drop the butter, make it 6 Maggi",
        session=seeded_session,
    )
    assert "Updated draft" in resp3.text
    assert "remove_bill_item" in resp3.tools_called or "update_bill_item" in resp3.tools_called

    # Step 4: Attempt oversell
    # Finalize bill when requested quantity is greater than stock
    # First let's create a separate chat attempting to sell 9999 packets of Tata Salt
    oversell_chat = 88888
    orchestrator.process_message(oversell_chat, "make a bill: 500 Tata Salt, UPI", seeded_session)
    resp4 = orchestrator.process_message(oversell_chat, "finalize", seeded_session)
    assert "Cannot complete" in resp4.text or "Insufficient" in resp4.text

    # Finalize the valid draft in chat_id
    resp_fin = orchestrator.process_message(chat_id, "finalize", seeded_session)
    assert "finalized successfully" in resp_fin.text

    # Step 5: Khata cycle
    # "put ₹500 on Ramesh's credit"
    resp_k1 = orchestrator.process_message(chat_id, "put ₹500 on Ramesh's credit", seeded_session)
    assert "500" in resp_k1.text
    assert "add_khata_credit" in resp_k1.tools_called

    # "Ramesh paid ₹300"
    resp_k2 = orchestrator.process_message(chat_id, "Ramesh paid ₹300", seeded_session)
    assert "200" in resp_k2.text or "repayment" in resp_k2.text
    assert "record_khata_payment" in resp_k2.tools_called

    # "Ramesh's balance?"
    resp_k3 = orchestrator.process_message(chat_id, "Ramesh's balance?", seeded_session)
    assert "200" in resp_k3.text

    # Step 6: Generate PDF invoice
    # "send me that bill as a PDF"
    resp6 = orchestrator.process_message(chat_id, "send me that bill as a PDF", seeded_session)
    assert len(resp6.artifacts) > 0
    assert resp6.artifacts[0]["type"] == "pdf_invoice"
    assert resp6.artifacts[0]["file_path"].endswith(".pdf")

    # Step 7: Generate PPTX analysis deck
    # "make this week's sales analysis deck"
    resp7 = orchestrator.process_message(chat_id, "make this week's sales analysis deck", seeded_session)
    assert len(resp7.artifacts) > 0
    assert resp7.artifacts[0]["type"] == "pptx_deck"
    assert resp7.artifacts[0]["file_path"].endswith(".pptx")

    # Step 8: Set a preference
    # "always assume UPI unless I say cash"
    resp8 = orchestrator.process_message(chat_id, "always assume UPI unless I say cash", seeded_session)
    assert "UPI" in resp8.text
    assert "set_preference" in resp8.tools_called

    # Step 9: Start /new chat
    resp9 = orchestrator.process_message(chat_id, "/new", seeded_session)
    assert "reset" in resp9.text.lower() or "new conversation" in resp9.text.lower()

    # Step 10: Demonstrate preference is remembered
    from app.services.preference_service import PreferenceService
    pref_svc = PreferenceService(seeded_session)
    assert pref_svc.get_preference("default_payment") == "UPI"
