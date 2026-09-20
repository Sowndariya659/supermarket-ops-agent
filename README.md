# Supermarket Ops Agent – Nebula KnowLab

An autonomous, agent-first AI system designed to operate a small Indian supermarket / kirana store entirely through a Telegram conversational interface.

---

## 1. Problem Statement & Philosophy

Operating an Indian kirana involves high-frequency, multi-turn, multi-entity transactions: loose vs packaged items, receiving supplier shipments with varying cost prices and MRPs, tracking customer credit (*Khata*) ledgers, calculating multi-slab GST (CGST + SGST), preventing overselling during busy rush hours, and generating formal business artifacts (PDF invoices and weekly analysis decks).

### Why an Agent, NOT a CRUD App with an LLM Wrapper:
A typical CRUD wrapper relies on hardcoded intent matching (`if 'bill' in text: ...`) or rigid state machines (Node-per-command graphs like LangGraph). Such approaches fail in messy retail environments:
1. **Dynamic Tool Orchestration**: When a shopkeeper says: *"50 packets of Maggi came in, cost ₹12, MRP ₹14, drop the butter from the open bill, and what is Ramesh's balance?"*, a rigid router collapses. An autonomous agent inspects tool schemas, performs multiple tool calls in an execution chain, and consolidates the outcome.
2. **Business Invariants in the Backend**: The LLM is never trusted to perform mathematical calculations, decrement inventory counters, or enforce price constraints. Instead, the LLM acts as the reasoning engine that calls strictly validated backend services where invariants (zero overselling, atomic decrements, Decimal GST math, append-only ledgers) are enforced in database transactions.

---

## 2. System Architecture

```
                       ┌─────────────────────────┐
                       │  Telegram User / Chat   │
                       └────────────┬────────────┘
                                    │ (Telegram Bot API - Webhook / Polling)
                                    ▼
                       ┌─────────────────────────┐
                       │    Telegram Handler     │
                       │ (Idempotency & Session) │
                       └────────────┬────────────┘
                                    │
                                    ▼
                       ┌─────────────────────────┐
                       │   Agent Orchestrator    │
                       │  (LLM Tool Calling Loop)│
                       └─────┬──────────────┬────┘
                             │              │
        ┌────────────────────┴───┐      ┌───┴────────────────────┐
        │     Typed Tools        │      │    Artifact Tools      │
        │ - Inventory Tools      │      │ - ReportLab PDF        │
        │ - Billing Tools        │      │ - python-pptx & Charts │
        │ - Khata Tools          │      └────────────────────────┘
        │ - Preference Tools     │
        └────────────┬───────────┘
                     │
                     ▼
        ┌────────────────────────┐
        │     Service Layer      │
        │ - Atomic Transactions  │
        │ - Decimal GST Math     │
        │ - Concurrency Guards   │
        └────────────┬───────────┘
                     │
                     ▼
        ┌────────────────────────┐
        │  Database (SQLAlchemy) │
        │  PostgreSQL / SQLite   │
        └────────────────────────┘
```

### Module Layout:
```text
supermarket-ops-agent/
├── app/
│   ├── main.py                    # Entry point (FastAPI server + Telegram runner)
│   ├── config.py                  # Pydantic BaseSettings
│   ├── telegram/
│   │   ├── bot.py                 # Telegram Bot instance & lifecycle
│   │   └── handlers.py            # Deduplication, message router, document uploader
│   ├── agent/
│   │   ├── orchestrator.py        # Multi-turn LLM reasoning loop & tool dispatcher
│   │   ├── prompts.py             # Domain prompt, grounding invariants, formatting
│   │   └── tools.py               # Typed Pydantic tool definitions & execution
│   ├── database/
│   │   ├── db.py                  # Engine, WAL pragmas, session factories
│   │   ├── models.py              # Relational models with Decimal types & check constraints
│   │   └── repositories.py        # Atomic updates, locking primitives, GST math
│   ├── services/
│   │   ├── inventory_service.py   # Catalog search, stock receipt, low stock detection
│   │   ├── billing_service.py     # Multi-turn drafts, atomic finalization, stock safety
│   │   ├── khata_service.py       # Customer credit ledger & balance computation
│   │   ├── preference_service.py  # Persistent key-value memory
│   │   └── analytics_service.py   # Sales aggregations, revenue trends, top items
│   ├── artifacts/
│   │   ├── invoice_pdf.py         # ReportLab GST Tax Invoice generator
│   │   ├── analytics_deck.py      # python-pptx 6-slide executive deck generator
│   │   └── charts.py              # matplotlib chart generators (trend, top items, low stock)
│   └── seed/
│       └── seed_data.py           # Realistic FMCG catalog & sample customers
├── tests/                         # All 20 required tests + end-to-end integration demo flow
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── requirements.txt
└── README.md
```

---

## 3. Database Design

All financial amounts use `NUMERIC(12, 2)` (mapped to Python `Decimal`), and quantities use `NUMERIC(12, 3)` with explicit database check constraints:

1. **`products`**: `id`, `name`, `sku`, `brand`, `unit`, `is_loose`, `hsn_code`, `gst_rate`, `cost_price`, `sell_price`, `mrp`, `reorder_level`, `created_at`, `updated_at`.
   - Constraints: `cost_price >= 0`, `sell_price >= 0`, `mrp >= 0`, `gst_rate >= 0`.
2. **`inventory`**: `product_id` (PK, FK), `quantity` (`CHECK (quantity >= 0)`), `updated_at`.
3. **`bills`**: `id`, `bill_number` (Unique), `telegram_chat_id`, `status` (`DRAFT`, `FINALIZED`, `CANCELLED`), `subtotal`, `cgst`, `sgst`, `total_tax`, `grand_total`, `payment_mode`, `payment_reference`, `customer_id` (FK), `idempotency_key` (Unique), `created_at`, `finalized_at`.
4. **`bill_items`**: `id`, `bill_id` (FK), `product_id` (FK), `quantity`, `unit_price`, `gst_rate`, `taxable_amount`, `cgst`, `sgst`, `total`.
   - Constraints: `quantity > 0`, `unit_price >= 0`, Unique constraint on `(bill_id, product_id)`.
5. **`customers`**: `id`, `name`, `phone`, `created_at`.
6. **`khata_transactions`**: Append-only customer debt ledger.
   - `id`, `customer_id` (FK), `transaction_type` (`CREDIT` / `PAYMENT`), `amount` (`CHECK (amount > 0)`), `reference`, `created_at`.
7. **`owner_preferences`**: Key-value memory surviving restarts. `id`, `key` (Unique), `value`, `updated_at`.
8. **`processed_telegram_updates`**: `telegram_update_id` (PK), `processed_at`.

---

## 4. Engineering Invariants & Correctness

### Concurrency & Stock Safety (Zero Overselling)
Stock is never decremented during draft operations. When `finalize_bill` executes:
1. All bill items are ordered by `product_id` to prevent deadlock across concurrent bills.
2. An atomic SQL conditional update is executed:
   ```sql
   UPDATE inventory
   SET quantity = quantity - :quantity, updated_at = CURRENT_TIMESTAMP
   WHERE product_id = :product_id AND quantity >= :quantity;
   ```
3. If affected row count is 0, the entire transaction is immediately rolled back and an `InsufficientStockError` is raised, reporting exact requested vs available stock.
4. Concurrency test `test_17_concurrent_stock_deduction` validates that when two threads simultaneously attempt to purchase 4 and 3 units respectively when only 6 exist, exactly one succeeds and the second fails safely with stock remaining at $\ge 0$.

### Strict Idempotency
- Duplicate Telegram update deliveries are intercepted at the gateway via `processed_telegram_updates`.
- Bill finalization accepts an `idempotency_key`. If the key was already finalized, the existing bill is returned without repeating inventory decrements or ledger writes.

### GST Calculation Engine
Intra-state GST splitting complies with statutory Indian tax calculations:
- Items priced at MRP (tax-inclusive):
  $$\text{Taxable Amount} = \text{Round}\left(\frac{\text{Quantity} \times \text{Unit Price}}{1 + \text{GST Rate}/100}, 2\right)$$
  $$\text{Total GST} = (\text{Quantity} \times \text{Unit Price}) - \text{Taxable Amount}$$
  $$\text{CGST} = \text{Round}\left(\frac{\text{Total GST}}{2}, 2\right), \quad \text{SGST} = \text{Total GST} - \text{CGST}$$
- Zero floating-point arithmetic. All calculations use `Decimal` with `ROUND_HALF_UP`.

### Ledger-Based Khata
Customer balances are never stored as a mutable number. Balances are derived dynamically from the immutable ledger:
$$\text{Outstanding Balance} = \sum \text{CREDIT} - \sum \text{PAYMENT}$$

---

## 5. Artifacts

- **Tax Invoice PDF**: Generated via ReportLab. Includes shop name, GSTIN, invoice number, itemized table with HSN, GST rate, CGST, SGST, subtotal, and totals. Sent directly via Telegram's `send_document`.
- **Business Review PPTX**: Generated via `python-pptx`. Contains a 6-slide executive deck with real database figures and 3 embedded `matplotlib` charts (Daily Sales Trend, Top Products, Low Stock Alerts).

---

## 6. Automated Testing

All 20 required assignment test scenarios + end-to-end integration demo flow are implemented and passing:

```bash
python -m pytest tests/ -v
```

### Test Suite Coverage:
- `test_01_product_creation`: Product creation with pricing, GST, stock.
- `test_02_stock_receiving`: Receiving shipments and updating MRP/cost.
- `test_03_stock_query`: Stock checking by ID and keyword.
- `test_04_low_stock_detection`: Threshold detection for reorder alerts.
- `test_05_basic_billing`: Draft creation and atomic finalization.
- `test_06_multi_turn_billing`: Multi-turn state preservation per chat.
- `test_07_bill_editing`: Updating quantities and dropping items.
- `test_08_gst_calculation`: Exact Decimal tax and CGST/SGST split.
- `test_09_oversell_rejection`: Rejecting finalization when stock is insufficient.
- `test_10_selling_below_cost`: Guardrail preventing sales below cost price.
- `test_11_khata_credit`: Recording credit ledger transactions.
- `test_12_khata_payment`: Recording customer repayments.
- `test_13_khata_balance_ledger_derived`: Deriving balances from transaction history.
- `test_14_pdf_generation`: ReportLab invoice generation.
- `test_15_pptx_generation`: python-pptx analysis deck with embedded charts.
- `test_16_idempotent_finalization`: Duplicate finalization requests.
- `test_17_concurrent_stock_deduction`: Multi-threaded race condition safety.
- `test_18_persistence_after_restart`: SQLite database restart durability.
- `test_19_preference_persistence`: Persistent owner preferences.
- `test_20_duplicate_telegram_update_handling`: Telegram update deduplication.
- `test_complete_10_step_demo_flow`: Full Section 23 10-step conversational sequence.

---

## 7. Setup & Execution

### Prerequisites:
- Python 3.11+
- Telegram Bot Token (from `@BotFather`)
- OpenAI / Gemini API Key (Optional for offline demo mode)

### Local Setup:
```bash
# 1. Clone or navigate to the project
cd supermarket-ops-agent

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy and configure environment variables
cp .env.example .env

# 4. Seed initial supermarket inventory
python -m app.seed.seed_data

# 5. Run automated tests
pytest

# 6. Run Telegram Bot in polling mode
python -m app.main polling

# Alternatively, run FastAPI web server:
python -m app.main
```

### Docker Deployment:
```bash
docker-compose up --build -d
```
The FastAPI health endpoint is available at `http://localhost:8000/health`.

---

## 8. Telegram Conversational Demo Flow

1. **Stock In**: *"50 packets of Maggi came in, cost ₹12, MRP ₹14"*
2. **Draft Bill**: *"make a bill: 2kg sugar, 1 Aashirvaad atta, 4 Maggi, 1 Amul butter, UPI"*
3. **Edit Draft**: *"drop the butter, make it 6 Maggi"*
4. **Finalize**: *"finalize bill"*
5. **Oversell Guard**: Attempting to bill beyond remaining stock is rejected with stock availability details.
6. **Khata Credit**: *"put ₹500 on Ramesh's credit"*
7. **Khata Repayment**: *"Ramesh paid ₹300"*
8. **Khata Balance**: *"Ramesh's balance?"* -> ₹200 remaining debt.
9. **Invoice PDF**: *"send me that bill as a PDF"* -> Bot uploads generated PDF.
10. **Analysis Deck**: *"make this week's sales analysis deck"* -> Bot uploads PowerPoint presentation.
11. **Persistent Memory**: *"always assume UPI unless I say cash"* -> Persisted across sessions and `/new` chats.
