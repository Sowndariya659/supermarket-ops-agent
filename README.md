# 🛒 Kirana Ops Agent (Supermarket Assistant)

![Banner](https://via.placeholder.com/1000x300?text=Kirana+Ops+Agent)

A highly resilient, autonomous AI assistant designed to streamline operations for Indian Supermarkets and Kirana stores. Built with **FastAPI**, **SQLite**, and **Google Gemini**, this Telegram bot serves as a virtual store manager capable of handling billing, inventory management, Khata (credit) tracking, and multimodal image processing.

---

## ✨ Key Features

- 🧠 **Autonomous Conversational Billing:** Add, remove, and update items in a draft bill using natural language (e.g., *"Make a bill: 2kg sugar, 4 Maggi, and 1 butter"*).
- 📷 **Multimodal Vision:** Snap a photo of a handwritten grocery slip or supplier invoice, and the AI will automatically parse the items and add them to the bill or inventory.
- 📒 **Khata (Credit) Ledger:** Track customer debts and payments effortlessly. The agent remembers who owes what.
- 🛡️ **Resilient Fallback Engine:** Features a graceful degradation circuit breaker. If the AI API is overloaded or hits a quota limit, the bot instantly falls back to a deterministic semantic engine, ensuring zero downtime for store operations.
- 📊 **Analytics & Reporting:** Ask for end-of-day sales summaries, or generate automated PPTX decks and PDF tax invoices.
- 🌐 **Deploy Anywhere:** Fully containerized and optimized to run perfectly in GitHub Codespaces or locally.

---

## 🎥 Demo

[Watch the full demo video here!](https://github.com/user-attachments/assets/PLACEHOLDER-VIDEO-LINK)  
*(Note: Upload the video to GitHub and replace this link)*

### 📸 Screenshots

| Adding Items to Bill | Multimodal Vision | End of Day Summary |
|:---:|:---:|:---:|
| ![Billing](https://via.placeholder.com/300x500?text=Billing+Screenshot) | ![Vision](https://via.placeholder.com/300x500?text=Vision+Screenshot) | ![Analytics](https://via.placeholder.com/300x500?text=Analytics+Screenshot) |

---

## 🏗️ Architecture & Tech Stack

- **Backend:** Python 3.14, FastAPI, SQLAlchemy (SQLite)
- **AI Engine:** Google Gemini Flash (`gemini-flash-latest`), with strict schema-based tool calling.
- **Platform:** Telegram Bot API
- **Resilience:** Custom Circuit Breaker with automatic regex-fallback for rate limits (429) and timeouts.

---

## 🚀 Quick Setup (GitHub Codespaces)

The absolute fastest way to test this project is via GitHub Codespaces (zero local setup required).

1. Click **Code** -> **Codespaces** -> **Create codespace on main**.
2. Wait for the environment to build. 
3. **Configure Secrets:** 
   Go to your Codespace Settings and add the following repository secrets:
   - `TELEGRAM_BOT_TOKEN` = *Your Telegram Bot Token*
   - `LLM_API_KEY` = *Your Google Gemini API Key*
4. Open the terminal and run:
   ```bash
   python demo_tour.py
   ```
5. Open Telegram and start chatting with your bot!

## 💻 Local Setup

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
3. Create a `.env` file in the root directory:
   ```env
   TELEGRAM_BOT_TOKEN=your_token_here
   LLM_API_KEY=your_gemini_key_here
   LLM_MODEL=gemini-3-flash-preview
   ```
4. Run the database seed and start the bot:
   ```bash
   python demo_tour.py
   ```
