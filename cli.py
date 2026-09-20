"""Interactive CLI mode for testing the Supermarket Ops Agent directly from the terminal."""

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.database.db import init_db, get_db
from app.seed.seed_data import seed_database
from app.agent.orchestrator import AgentOrchestrator


def run_interactive_cli():
    print("=" * 65)
    print("Supermarket Ops Agent - Interactive Terminal Mode")
    print("=" * 65)
    print("Initializing and seeding database...")
    init_db()
    with get_db() as session:
        seed_database(session)

    orchestrator = AgentOrchestrator()
    chat_id = 123456

    print("\nReady! Try entering commands like:")
    print(" - 'how much sugar is left?'")
    print(" - 'what's running out?'")
    print(" - '50 packets of Maggi came in, cost 12, MRP 14'")
    print(" - 'make a bill: 2kg sugar, 1 Aashirvaad atta, 4 Maggi, UPI'")
    print(" - 'drop the butter, make it 6 Maggi'")
    print(" - 'finalize'")
    print(" - 'put 500 on Ramesh\\'s credit'")
    print(" - 'Ramesh paid 300'")
    print(" - 'Ramesh\\'s balance?'")
    print(" - 'today\\'s sales?'")
    print(" - 'send me that bill as a PDF'")
    print(" - 'make this week\\'s sales analysis deck'")
    print(" - '/new' to reset chat")
    print(" - 'exit' to quit\n")

    # If arguments were passed via command line, execute them and exit
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        print(f"Shopkeeper: {query}")
        with get_db() as session:
            resp = orchestrator.process_message(chat_id, query, session)
        print(f"\nAgent:\n{resp.text}")
        for art in resp.artifacts:
            print(f"\n[Generated Artifact ({art.get('type')}): {art.get('file_path')}]")
        return

    # Interactive loop
    while True:
        try:
            user_input = input("\nShopkeeper > ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q"):
                print("Exiting Supermarket Ops Agent. Goodbye!")
                break

            with get_db() as session:
                resp = orchestrator.process_message(chat_id, user_input, session)

            print(f"\nAgent:\n{resp.text}")
            for art in resp.artifacts:
                print(f"\n[Generated Artifact ({art.get('type')}): {art.get('file_path')}]")

        except (KeyboardInterrupt, EOFError):
            print("\nSession ended.")
            break


if __name__ == "__main__":
    run_interactive_cli()
