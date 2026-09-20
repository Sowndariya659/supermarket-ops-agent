"""Typed tools and schemas for LLM Agent tool-calling."""

from decimal import Decimal
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.database.repositories import InsufficientStockError, BelowCostPriceError
from app.services.inventory_service import InventoryService
from app.services.billing_service import BillingService
from app.services.khata_service import KhataService
from app.services.preference_service import PreferenceService
from app.services.analytics_service import AnalyticsService
from app.artifacts.invoice_pdf import generate_invoice_pdf
from app.artifacts.analytics_deck import generate_analysis_pptx


class AgentToolContext:
    def __init__(self, session: Session, chat_id: int):
        self.session = session
        self.chat_id = chat_id
        self.inventory_svc = InventoryService(session)
        self.billing_svc = BillingService(session)
        self.khata_svc = KhataService(session)
        self.pref_svc = PreferenceService(session)
        self.analytics_svc = AnalyticsService(session)


def get_tool_definitions() -> List[Dict[str, Any]]:
    """OpenAI/Gemini compatible function call definitions."""
    return [
        {
            "name": "search_products",
            "description": "Search products in the supermarket database by name, brand, or category. ALWAYS use this tool to ground any product mentioned by the user before billing, checking stock, or receiving stock.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Product search keywords (e.g. 'sugar', 'Maggi', 'atta', 'oil')"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return (default: 5)"
                    }
                },
                "required": ["query"]
            }
        },
        {
            "name": "add_product",
            "description": "Add a new product to the supermarket catalog when a customer asks to register an item.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Full product name (e.g. 'Amul Butter 100g')"},
                    "mrp": {"type": "number", "description": "Maximum Retail Price in INR"},
                    "cost_price": {"type": "number", "description": "Cost/Purchase price from supplier in INR"},
                    "sell_price": {"type": "number", "description": "Selling price to customer in INR (usually equal to MRP)"},
                    "gst_rate": {"type": "number", "description": "GST rate percentage (e.g. 0, 5, 12, 18, 28)"},
                    "unit": {"type": "string", "description": "Unit of measurement (packet, kg, g, L, piece)"},
                    "hsn_code": {"type": "string", "description": "HSN Code if known, or default '1904'"},
                    "is_loose": {"type": "boolean", "description": "True if loose commodity (sugar/rice), False if packaged"},
                    "reorder_level": {"type": "number", "description": "Minimum stock quantity threshold for alerts"},
                    "initial_stock": {"type": "number", "description": "Initial stock quantity (default 0)"}
                },
                "required": ["name", "mrp", "cost_price", "sell_price", "gst_rate"]
            }
        },
        {
            "name": "receive_stock",
            "description": "Record received supplier stock shipment for an existing product. Updates inventory quantity and optionally cost price and MRP.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "integer", "description": "Exact Product ID from search_products"},
                    "quantity": {"type": "number", "description": "Number of units received"},
                    "cost_price": {"type": "number", "description": "Supplier cost per unit in INR (optional)"},
                    "mrp": {"type": "number", "description": "New MRP in INR (optional)"}
                },
                "required": ["product_id", "quantity"]
            }
        },
        {
            "name": "get_stock",
            "description": "Check current stock level for a product by product_id or query name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "integer", "description": "Product ID if known"},
                    "query": {"type": "string", "description": "Search keyword if product ID is unknown"}
                }
            }
        },
        {
            "name": "get_low_stock",
            "description": "List all products that are running low (stock <= reorder_level).",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        },
        {
            "name": "create_or_get_draft_bill",
            "description": "Create or fetch an active draft bill for the current conversation. Does NOT decrement stock.",
            "parameters": {
                "type": "object",
                "properties": {
                    "payment_mode": {"type": "string", "description": "Payment mode: UPI, CASH, KHATA, etc."},
                    "customer_name": {"type": "string", "description": "Optional customer name to associate with the bill"}
                }
            }
        },
        {
            "name": "add_bill_item",
            "description": "Add an item to the active draft bill. If item already exists, quantity is incremented. Stock is NOT decremented until finalization.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "integer", "description": "Product ID to add"},
                    "quantity": {"type": "number", "description": "Quantity to add"},
                    "unit_price": {"type": "number", "description": "Optional custom sell price (must be >= cost price)"}
                },
                "required": ["product_id", "quantity"]
            }
        },
        {
            "name": "update_bill_item",
            "description": "Update/replace the quantity of an item in the active draft bill (e.g. 'make it 6 Maggi').",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "integer", "description": "Product ID to update"},
                    "quantity": {"type": "number", "description": "New total quantity for this item"}
                },
                "required": ["product_id", "quantity"]
            }
        },
        {
            "name": "remove_bill_item",
            "description": "Remove an item from the active draft bill (e.g. 'drop the butter').",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "integer", "description": "Product ID to remove from bill"}
                },
                "required": ["product_id"]
            }
        },
        {
            "name": "get_current_bill",
            "description": "View the current draft bill, items, and tax totals.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        },
        {
            "name": "finalize_bill",
            "description": "Finalize and commit the current draft bill. Validates inventory, atomically decrements stock, creates customer Khata debit if payment is KHATA, and marks bill FINALIZED. Fails if insufficient stock.",
            "parameters": {
                "type": "object",
                "properties": {
                    "payment_mode": {"type": "string", "description": "Final payment mode (UPI, CASH, KHATA)"},
                    "payment_ref": {"type": "string", "description": "Transaction reference or UTR number if applicable"},
                    "idempotency_key": {"type": "string", "description": "Unique key to ensure idempotent execution"}
                }
            }
        },
        {
            "name": "cancel_current_bill",
            "description": "Cancel the active draft bill without decrementing any stock.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        },
        {
            "name": "find_customer",
            "description": "Search customers by name or phone number.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Customer name or phone"}
                },
                "required": ["query"]
            }
        },
        {
            "name": "add_khata_credit",
            "description": "Add goods credit to a customer's ledger (Customer owes shop money). Increases outstanding debt balance.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {"type": "string", "description": "Name of the customer (e.g. 'Ramesh')"},
                    "amount": {"type": "number", "description": "Amount in INR to put on credit"},
                    "reference": {"type": "string", "description": "Optional notes or item description"}
                },
                "required": ["customer_name", "amount"]
            }
        },
        {
            "name": "record_khata_payment",
            "description": "Record a payment made by a customer settling their khata debt. Decreases outstanding debt balance.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {"type": "string", "description": "Name of the customer (e.g. 'Ramesh')"},
                    "amount": {"type": "number", "description": "Amount in INR repaid by customer"},
                    "reference": {"type": "string", "description": "Payment mode/reference (e.g. 'Cash', 'GPay 1234')"}
                },
                "required": ["customer_name", "amount"]
            }
        },
        {
            "name": "get_khata_balance",
            "description": "Query the current outstanding ledger debt balance for a customer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {"type": "string", "description": "Name of the customer"}
                },
                "required": ["customer_name"]
            }
        },
        {
            "name": "get_sales_summary",
            "description": "Get sales and GST summary for 'today', 'yesterday', 'week', or 'month'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {"type": "string", "enum": ["today", "yesterday", "week", "month"], "description": "Period to summarize"}
                }
            }
        },
        {
            "name": "generate_invoice_pdf",
            "description": "Generate a professional GST tax invoice PDF for a finalized or current bill and prepare it to send to user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "bill_id": {"type": "integer", "description": "Bill ID to generate PDF for (optional, defaults to latest finalized or current bill)"}
                }
            }
        },
        {
            "name": "generate_analysis_pptx",
            "description": "Generate a PowerPoint (.pptx) sales analysis deck with real database data and charts for 'week' or 'month'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {"type": "string", "enum": ["week", "month"], "description": "Reporting period (default: week)"}
                }
            }
        },
        {
            "name": "set_preference",
            "description": "Set a persistent shop preference or default setting (e.g. 'default_payment', 'shop_name', 'gstin', 'default_atta'). Persists across sessions and restarts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Preference key name"},
                    "value": {"type": "string", "description": "Preference value to store"}
                },
                "required": ["key", "value"]
            }
        },
        {
            "name": "get_preference",
            "description": "Retrieve a stored persistent preference value by key.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Preference key to look up"}
                },
                "required": ["key"]
            }
        },
        {
            "name": "list_products",
            "description": "List all products available in the supermarket catalog with their stock and prices.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Maximum products to return (default 50)"}
                }
            }
        },
        {
            "name": "close_the_day",
            "description": "Perform end-of-day register closure, reconcile cash vs UPI collections, summarize sales and profits, and list replenishment items.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    ]


def execute_tool(tool_name: str, args: Dict[str, Any], context: AgentToolContext) -> Dict[str, Any]:
    """Dispatch and execute a tool call within the database transaction context."""
    try:
        from datetime import datetime
        if tool_name == "search_products":
            return {"results": context.inventory_svc.search_products(query=args["query"], limit=args.get("limit", 5))}

        elif tool_name == "list_products":
            return {"products": context.inventory_svc.list_products(limit=args.get("limit", 50))}

        elif tool_name == "close_the_day":
            sales = context.analytics_svc.get_sales_summary(period="today")
            low_stock = context.inventory_svc.get_low_stock()
            return {
                "sales_summary": sales,
                "low_stock_alerts": low_stock,
                "closed_at": datetime.utcnow().strftime("%d-%b-%Y %I:%M %p"),
            }

        elif tool_name == "add_product":
            return {"product": context.inventory_svc.add_product(**args)}

        elif tool_name == "receive_stock":
            return context.inventory_svc.receive_stock(**args)

        elif tool_name == "get_stock":
            return context.inventory_svc.get_stock(product_id=args.get("product_id"), query=args.get("query"))

        elif tool_name == "get_low_stock":
            return {"low_stock_products": context.inventory_svc.get_low_stock()}

        elif tool_name == "create_or_get_draft_bill":
            return context.billing_svc.get_or_create_draft(
                chat_id=context.chat_id,
                payment_mode=args.get("payment_mode"),
                customer_name=args.get("customer_name")
            )

        elif tool_name in ("add_bill_item", "add_to_draft_bill"):
            prod_id = args.get("product_id")
            if not prod_id and "product_name" in args:
                prods = context.inventory_svc.search_products(args["product_name"])
                if prods:
                    prod_id = prods[0]["id"]
            if not prod_id:
                return {"error": f"Product '{args.get('product_name')}' not found."}
            return context.billing_svc.add_item(
                chat_id=context.chat_id,
                product_id=prod_id,
                quantity=args["quantity"],
                unit_price=args.get("unit_price")
            )

        elif tool_name == "update_bill_item":
            return context.billing_svc.update_item(
                chat_id=context.chat_id,
                product_id=args["product_id"],
                quantity=args["quantity"]
            )

        elif tool_name == "remove_bill_item":
            return context.billing_svc.remove_item(
                chat_id=context.chat_id,
                product_id=args["product_id"]
            )

        elif tool_name == "get_current_bill":
            bill = context.billing_svc.get_current_bill(chat_id=context.chat_id)
            return {"bill": bill} if bill else {"bill": None, "message": "No active draft bill found."}

        elif tool_name == "finalize_bill":
            return context.billing_svc.finalize_bill(
                chat_id=context.chat_id,
                payment_mode=args.get("payment_mode"),
                payment_ref=args.get("payment_ref"),
                idempotency_key=args.get("idempotency_key")
            )

        elif tool_name == "cancel_current_bill":
            return context.billing_svc.cancel_current_draft(chat_id=context.chat_id)

        elif tool_name == "find_customer":
            return {"customers": context.khata_svc.find_customers(query=args["query"])}

        elif tool_name == "add_khata_credit":
            return context.khata_svc.add_credit(
                customer_name_or_id=args["customer_name"],
                amount=args["amount"],
                reference=args.get("reference")
            )

        elif tool_name == "record_khata_payment":
            return context.khata_svc.record_payment(
                customer_name_or_id=args["customer_name"],
                amount=args["amount"],
                reference=args.get("reference")
            )

        elif tool_name == "get_khata_balance":
            return context.khata_svc.get_balance(customer_name_or_id=args["customer_name"])

        elif tool_name == "get_sales_summary":
            return context.analytics_svc.get_sales_summary(period=args.get("period", "today"))

        elif tool_name == "generate_invoice_pdf":
            bill_id = args.get("bill_id")
            if not bill_id:
                # Find current draft or latest finalized bill for chat
                draft = context.billing_svc.get_current_bill(chat_id=context.chat_id)
                if draft:
                    bill_id = draft["id"]
                else:
                    from app.database.models import Bill
                    last_bill = context.session.query(Bill).filter(Bill.telegram_chat_id == context.chat_id).order_by(Bill.id.desc()).first()
                    if last_bill:
                        bill_id = last_bill.id
                    else:
                        return {"error": "No bill found to generate invoice PDF."}

            filepath = generate_invoice_pdf(bill_id=bill_id, session=context.session)
            return {
                "generated": True,
                "bill_id": bill_id,
                "file_path": filepath,
                "type": "pdf_invoice"
            }

        elif tool_name == "generate_analysis_pptx":
            period = args.get("period", "week")
            filepath = generate_analysis_pptx(period=period, session=context.session)
            return {
                "generated": True,
                "period": period,
                "file_path": filepath,
                "type": "pptx_deck"
            }

        elif tool_name == "set_preference":
            return context.pref_svc.set_preference(key=args["key"], value=args["value"])

        elif tool_name == "get_preference":
            val = context.pref_svc.get_preference(key=args["key"])
            return {"key": args["key"], "value": val}

        else:
            return {"error": f"Unknown tool: '{tool_name}'"}

    except InsufficientStockError as e:
        return {
            "success": False,
            "error_type": "INSUFFICIENT_STOCK",
            "message": str(e),
            "product_name": e.product_name,
            "requested": float(e.requested),
            "available": float(e.available),
        }
    except BelowCostPriceError as e:
        return {
            "success": False,
            "error_type": "BELOW_COST_PRICE",
            "message": str(e),
            "product_name": e.product_name,
            "sell_price": float(e.sell_price),
            "cost_price": float(e.cost_price),
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
