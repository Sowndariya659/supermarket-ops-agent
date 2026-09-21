# 🛒 Kirana Ops Agent: Autonomous Supermarket Assistant

[![Python](https://img.shields.io/badge/Python-3.14+-blue.svg)](https://www.python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com)
[![Google Gemini](https://img.shields.io/badge/AI-Google_Gemini_Flash-orange.svg)](https://ai.google.dev)
[![Deployed](https://img.shields.io/badge/Deployed_Via-GitHub_Codespaces-black.svg?logo=github)](https://github.com/features/codespaces)

An enterprise-grade, highly resilient Autonomous AI Assistant designed specifically to streamline operations for Indian Supermarkets and Kirana stores. Built to function as a virtual store manager, it handles conversational billing, inventory management, Khata (credit) tracking, and multimodal image processing directly through Telegram.

---

## ✨ Core Capabilities

- 🧠 **Autonomous Conversational Billing:** Create and modify bills using natural language. The AI understands context and complex queries (e.g., *"Make a bill: 2kg sugar, 4 Maggi, and 1 butter"* or *"Wait, make the Maggi 6 instead"*).
- 📷 **Multimodal Vision Parsing:** Snap a photo of a handwritten grocery slip, distributor invoice, or product packaging. The AI will automatically extract the items, quantities, and prices to update inventory or draft bills.
- 📒 **Khata (Credit) Ledger:** Track customer debts and repayments effortlessly. The agent maintains ledger balances and associates them with active bills.
- 🛡️ **Resilient Fallback Engine:** Features a graceful degradation circuit breaker. If the AI API is overloaded (503) or hits a quota limit (429), the bot instantly and silently falls back to a deterministic semantic engine. **Zero downtime for store operations.**
- 📊 **Analytics & Reporting:** Ask for end-of-day sales summaries, and the bot will dynamically generate downloadable PPTX analysis decks and PDF tax invoices.

---

## 📸 Feature Showcase

| 🛒 Conversational Billing | 📷 Multimodal Vision | 📊 End of Day Summary |
|:---:|:---:|:---:|
| <img src="assets/Screenshot%202026-09-21%20211911.png" width="250"/> | <img src="assets/Screenshot%202026-09-21%20211921.png" width="250"/> | <img src="assets/Screenshot%202026-09-21%20211938.png" width="250"/> |

| 📒 Khata (Credit) Tracking | 📦 Inventory Management | 🛡️ Fallback Resilience |
|:---:|:---:|:---:|
| <img src="assets/Screenshot%202026-09-21%20211948.png" width="250"/> | <img src="assets/Screenshot%202026-09-21%20211956.png" width="250"/> | <img src="assets/Screenshot%202026-09-21%20212008.png" width="250"/> |

---

## 🚀 How to Run (For Evaluators)

This project is fully deployed and configured to run instantly via **GitHub Codespaces**. 

As a collaborator on this repository, **you do not need to configure any API keys or `.env` files.** The necessary Telegram and Google Gemini secrets are securely pre-loaded as Repository Secrets for seamless evaluation.

### Option 1: ☁️ Run via GitHub Codespaces (Recommended - Zero Setup)

1. Click the **Code** button at the top of this repository.
2. Select the **Codespaces** tab.
3. Click **Create codespace on main**.
4. Wait a few seconds for the environment to build.
5. In the terminal that appears at the bottom of the screen, run the following command:
   ```bash
   python demo_tour.py
   ```
6. Open Telegram and search for the bot (or use the link provided in the terminal output) and start chatting!

*(Note: If you encounter a `Conflict` error, ensure you don't have multiple Codespace terminal tabs running the bot at the same time. You can kill existing processes by typing `pkill -f python`).*

### Option 2: 💻 Run Locally

If you prefer to run the project on your local machine, follow these steps:

1. Clone the repository:
   ```bash
   git clone https://github.com/Sowndariya659/supermarket-ops-agent.git
   cd supermarket-ops-agent
   ```
2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Create a `.env` file in the root directory and add your keys:
   ```env
   TELEGRAM_BOT_TOKEN=your_telegram_token_here
   LLM_API_KEY=your_gemini_api_key_here
   LLM_MODEL=gemini-3-flash-preview
   ```
4. Run the application:
   ```bash
   python demo_tour.py
   ```

---

## 🏗️ Technical Architecture

- **Backend Framework:** FastAPI / Python 3.14
- **Database:** SQLite with SQLAlchemy ORM (Transactional safety for inventory decrementing)
- **AI Integration:** Google Gemini Multimodal APIs (`gemini-3-flash-preview`), enforcing strict JSON schema-based tool calling.
- **Frontend / Interface:** Telegram Bot API (via `python-telegram-bot` webhook/polling fallback)
- **Deployment Strategy:** Cloud-native architecture, ready for containerization (Dockerfile included) and currently optimized for GitHub Codespaces.

---

*Developed as a capstone project for Kirana automation and AI integration.*
