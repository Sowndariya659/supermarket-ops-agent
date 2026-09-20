"""Automated end-to-end demo tour of the Supermarket Ops Agent."""

import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.database.db import init_db, get_db
from app.seed.seed_data import seed_database
from app.agent.orchestrator import AgentOrchestrator


def run_demo_tour():
    print("=" * 70)
    print("RUNNING END-TO-END SUPERMARKET OPS AGENT DEMO")
    print("=" * 70)

    init_db()
    with get_db() as s:
        seed_database(s)

    orchestrator = AgentOrchestrator()
    chat_id = 77777

    steps = [
        ("Step 1: Check Current Stock", "how much sugar is left?"),
        ("Step 2: Check Low Stock Alerts", "what's running out?"),
        ("Step 3: Receive Supplier Shipment", "50 packets of Maggi came in, cost 12, MRP 14"),
        ("Step 4: Create Multi-item Draft Bill", "make a bill: 2kg sugar, 1 Aashirvaad atta, 4 Maggi, 1 Amul butter, UPI"),
        ("Step 5: Conversational Draft Editing", "drop the butter, make it 6 Maggi"),
        ("Step 6: Finalize Bill & Commit Stock", "finalize"),
        ("Step 7: Customer Khata Credit", "put 500 on Ramesh's credit"),
        ("Step 8: Customer Repayment", "Ramesh paid 300"),
        ("Step 9: Customer Balance Ledger Query", "Ramesh's balance?"),
        ("Step 10: Today's Sales Analytics", "today's sales?"),
        ("Step 11: Generate Tax Invoice PDF", "send me that bill as a PDF"),
        ("Step 12: Generate PowerPoint Analysis Deck", "make this week's sales analysis deck"),
        ("Step 13: Persistent Shop Preference", "always assume UPI unless I say cash"),
    ]

    for title, message in steps:
        print(f"\n[+] {title}")
        print(f"Shopkeeper: \"{message}\"")
        with get_db() as s:
            resp = orchestrator.process_message(chat_id, message, s)
        print(f"Agent:\n{resp.text}")
        if resp.artifacts:
            for art in resp.artifacts:
                print(f"   -> Artifact Generated: {art.get('type')} => {art.get('file_path')}")
        time.sleep(0.1)

    print("\n" + "=" * 70)
    print("DEMO TOUR COMPLETED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    run_demo_tour()
