# 🏗️ Kirana Ops Agent — Architecture

```mermaid
flowchart LR
    U([Store Operator]) -->|message / photo| T[Telegram Bot]
    T --> A[FastAPI App]
    A --> R[Request Router]
    R --> G{Gemini Available?}

    G -->|Yes| AI[Google Gemini
multimodal + structured tools]
    G -->|No / 429 / 503| F[Fallback Logic]

    AI --> O[Billing + Inventory + Khata + Analytics]
    F --> O
    O --> D[(SQLite / SQLAlchemy)]
    O --> P[PDF / PPTX Reports]
    P --> T
    O -->|response| A
    A -->|reply| T

    classDef user fill:#111827,stroke:#111827,color:#fff;
    classDef interface fill:#dbeafe,stroke:#2563eb,color:#0f172a;
    classDef app fill:#ede9fe,stroke:#7c3aed,color:#1f2937;
    classDef ai fill:#dcfce7,stroke:#16a34a,color:#14532d;
    classDef data fill:#fef3c7,stroke:#d97706,color:#78350f;
    classDef report fill:#fee2e2,stroke:#dc2626,color:#7f1d1d;
    classDef decision fill:#f3f4f6,stroke:#6b7280,color:#111827;

    class U user;
    class T interface;
    class A,R app;
    class G decision;
    class AI,F,O ai;
    class D data;
    class P report;
```

This is a simple runtime view of the system:

- Operator sends messages/photos in Telegram.
- FastAPI handles the request and routes it.
- Gemini is used for multimodal understanding and structured actions when available.
- A fallback path handles service overload or quota errors.
- Billing, inventory, Khata, and analytics logic update SQLite through SQLAlchemy.
- Reports are generated as PDFs/PPTX files and sent back to Telegram.
