"""Tests for Multimodal Image & Handwritten Slip Processing."""

import pytest
from unittest.mock import patch, MagicMock
from decimal import Decimal

from app.database.models import Product, Inventory
from app.services.inventory_service import InventoryService
from app.services.billing_service import BillingService
from app.agent.orchestrator import AgentOrchestrator


def test_vision_multimodal_process_image_success(db_session):
    """Verify that process_image triggers Gemini multimodal and executes tool calls."""
    # Seed products
    inv_svc = InventoryService(db_session)
    p1 = inv_svc.add_product(
        name="Maggi 2-Minute Noodles 70g",
        mrp=14.0,
        cost_price=10.0,
        sell_price=14.0,
        gst_rate=5.0,
        unit="packet",
        initial_stock=50.0,
    )

    orchestrator = AgentOrchestrator()
    chat_id = 998877

    # Dummy image bytes
    dummy_image = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00"

    # Mock response from Gemini API with function calls
    mock_gemini_turn1 = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "functionCall": {
                                "name": "add_to_draft_bill",
                                "args": {
                                    "product_name": "Maggi 2-Minute Noodles 70g",
                                    "quantity": 3
                                }
                            }
                        }
                    ]
                }
            }
        ]
    }

    mock_gemini_turn2 = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": "I analyzed the handwritten slip and added 3 packets of Maggi Noodles to the bill."
                        }
                    ]
                }
            }
        ]
    }

    with patch("httpx.Client.post") as mock_post:
        resp1 = MagicMock()
        resp1.status_code = 200
        resp1.json.return_value = mock_gemini_turn1

        resp2 = MagicMock()
        resp2.status_code = 200
        resp2.json.return_value = mock_gemini_turn2

        mock_post.side_effect = [resp1, resp2]

        with patch("app.config.settings.LLM_API_KEY", "AQ.test_fake_gemini_key"):
            response = orchestrator.process_image(
                chat_id=chat_id,
                image_bytes=dummy_image,
                mime_type="image/jpeg",
                caption="Please add these grocery items to bill",
                session=db_session,
            )

    assert "Maggi" in response.text
    assert "add_to_draft_bill" in response.tools_called

    # Verify item was actually added to draft bill in DB
    billing_svc = BillingService(db_session)
    draft = billing_svc.get_current_bill(chat_id)
    assert draft is not None
    assert len(draft["items"]) == 1
    assert draft["items"][0]["quantity"] == 3


def test_vision_fallback_when_no_api_key(db_session):
    """Verify clean response when no LLM key is set."""
    orchestrator = AgentOrchestrator()
    dummy_image = b"sample_bytes"

    with patch("app.config.settings.LLM_API_KEY", ""):
        response = orchestrator.process_image(
            chat_id=12345,
            image_bytes=dummy_image,
            session=db_session,
        )

    assert "LLM_API_KEY" in response.text
