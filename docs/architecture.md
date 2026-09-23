# 🏗️ Kirana Ops Agent — Architecture Diagram

This diagram shows the main runtime flow from a store operator using Telegram through the application services, AI integrations, persistence layer, and generated reports.

```mermaid
flowchart TB
    %% Clients and deployment
    operator["Store operator / cashier"]
    telegram["Telegram Bot API\npython-telegram-bot"]
    codespaces["GitHub Codespaces\npython -m app.main"]

    %% Application boundary
    subgraph app["Kirana Ops Agent — Python application"]
        entry["Application entrypoint\nFastAPI + bot polling/webhook"]
        router["Message & media router"]
        context["Conversation context\nvalidation + JSON tool schema"]
        breaker["Resilient fallback engine\ncircuit breaker for 429/503"]

        subgraph domain["Store operations"]
            billing["Conversational billing"]
            inventory["Inventory management"]
            khata["Khata credit ledger"]
            analytics["Sales analytics & summaries"]
        end

        reports["Report generators\nPDF invoices + PPTX decks"]
        orm["SQLAlchemy ORM\ntransaction boundaries"]
    end

    %% External services and storage
    gemini["Google Gemini multimodal API\ngemini-3-flash-preview"]
    sqlite[("SQLite database")]
    artifacts[("Generated documents\nPDF / PPTX")]
    secrets["Repository secrets / .env\nTelegram token + LLM API key"]

    operator -->|text, photos, invoices| telegram
    telegram <--> |messages, images, replies| entry
    codespaces --> entry
    secrets -. configuration .-> entry

    entry --> router
    router --> context
    context --> breaker
    breaker -->|normal path| gemini
    breaker -->|quota/outage| domain
    gemini -->|structured tool calls / vision extraction| context
    context --> domain

    billing -->|create/update bill| orm
    inventory -->|stock lookup & atomic decrement| orm
    khata -->|debt / repayment ledger| orm
    analytics -->|sales queries| orm
    orm <--> sqlite

    billing --> reports
    analytics --> reports
    reports --> artifacts
    artifacts -->|downloadable invoice / analysis| telegram
    domain -->|operational response| entry
    entry -->|reply| telegram

    classDef external fill:#fff3e0,stroke:#e65100,color:#4e342e;
    classDef app fill:#e3f2fd,stroke:#1565c0,color:#0d47a1;
    classDef data fill:#e8f5e9,stroke:#2e7d32,color:#1b5e20;
    classDef resilience fill:#fce4ec,stroke:#ad1457,color:#880e4f;

    class operator,telegram,codespaces,gemini,secrets external;
    class entry,router,context,billing,inventory,khata,analytics,reports app;
    class sqlite,artifacts,orm data;
    class breaker resilience;
```

## Request flow

1. A cashier sends text or an image through Telegram.
2. The Python application routes the message and builds conversational context.
3. The fallback engine calls Gemini for natural-language understanding and multimodal extraction when the service is available.
4. Structured tool calls are dispatched to billing, inventory, Khata, or analytics services.
5. SQLAlchemy persists changes in SQLite, including transactional inventory updates.
6. PDF invoices and PPTX analysis decks are generated when requested and returned through Telegram.
7. When Gemini returns a quota or availability error (`429`/`503`), the circuit breaker routes the request to the resilient local fallback path instead of failing silently.

## Deployment boundary

The application runs with `python -m app.main` in GitHub Codespaces. Telegram and Gemini credentials are supplied through repository secrets in Codespaces or through a local `.env` file during local development.
