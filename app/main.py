"""FastAPI application entry point, lifecycle management, and Telegram webhook receiver."""

import sys
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response, status
from telegram import Update

from app.config import settings
from app.database.db import init_db, get_db
from app.database.models import Product
from app.seed.seed_data import seed_database
from app.telegram.bot import create_telegram_application, run_bot_polling

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
)
logger = logging.getLogger(__name__)

telegram_app = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    global telegram_app
    logger.info("Initializing database schema...")
    init_db()

    # Automatically seed database if empty
    with get_db() as session:
        count = session.query(Product).count()
        if count == 0:
            logger.info("Database empty, applying seed data...")
            seed_database(session)

    # Initialize Telegram app
    telegram_app = create_telegram_application()
    polling_active = False
    if telegram_app:
        if settings.WEBHOOK_URL:
            webhook_path = f"{settings.WEBHOOK_URL.rstrip('/')}/webhook"
            logger.info(f"Setting Telegram webhook: {webhook_path}")
            await telegram_app.initialize()
            await telegram_app.bot.set_webhook(url=webhook_path)
            await telegram_app.start()
        else:
            logger.info("Starting Telegram bot background polling runner inside web container...")
            await telegram_app.initialize()
            await telegram_app.start()
            await telegram_app.updater.start_polling()
            polling_active = True

    yield

    if telegram_app:
        if settings.WEBHOOK_URL:
            logger.info("Stopping Telegram webhook...")
            await telegram_app.stop()
            await telegram_app.shutdown()
        elif polling_active:
            logger.info("Stopping Telegram bot polling...")
            await telegram_app.updater.stop()
            await telegram_app.stop()
            await telegram_app.shutdown()


app = FastAPI(
    title=settings.APP_NAME,
    description="Conversational AI Agent for Indian Supermarket / Kirana operations via Telegram",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/")
def root():
    return {
        "message": f"Welcome to {settings.APP_NAME}",
        "status": "online",
        "docs_url": "/docs",
    }


@app.get("/health")
def health_check():
    """Health check endpoint for Docker and monitoring."""
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "database": settings.DATABASE_URL.split(":")[0],
    }


@app.post("/webhook")
async def telegram_webhook(request: Request):
    """Receive updates from Telegram Bot API in webhook mode."""
    global telegram_app
    if not telegram_app:
        return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)

    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return Response(status_code=status.HTTP_200_OK)


@app.post("/seed")
def trigger_seed():
    """Manually re-seed supermarket database."""
    init_db()
    with get_db() as session:
        seed_database(session)
    return {"status": "success", "message": "Database seeded successfully."}


if __name__ == "__main__":
    if "--polling" in sys.argv or "polling" in sys.argv:
        init_db()
        with get_db() as session:
            seed_database(session)
        run_bot_polling()
    else:
        import uvicorn
        uvicorn.run("app.main:app", host="0.0.0.0", port=settings.PORT, reload=settings.DEBUG)
