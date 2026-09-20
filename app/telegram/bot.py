"""Telegram bot application configuration and initialization."""

import logging
from typing import Optional
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from app.config import settings
from app.telegram.handlers import (
    start_handler,
    new_chat_handler,
    message_handler,
    callback_query_handler,
    voice_handler,
    photo_handler,
)

logger = logging.getLogger(__name__)


def create_telegram_application() -> Optional[Application]:
    """Create and configure the Telegram bot application instance."""
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN not configured. Bot will not connect to Telegram servers.")
        return None

    app = ApplicationBuilder().token(settings.TELEGRAM_BOT_TOKEN).build()

    # Register handlers
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", start_handler))
    app.add_handler(CommandHandler("new", new_chat_handler))
    app.add_handler(CommandHandler("reset", new_chat_handler))
    app.add_handler(CallbackQueryHandler(callback_query_handler))
    app.add_handler(MessageHandler(filters.VOICE, voice_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    return app


def run_bot_polling():
    """Run bot using long-polling for local development."""
    app = create_telegram_application()
    if not app:
        print("Cannot start polling: TELEGRAM_BOT_TOKEN is missing in .env")
        return

    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    logger.info("Starting Telegram bot in polling mode...")
    print("[BOT] Supermarket Ops Agent Telegram bot is polling for updates...")
    app.run_polling()
