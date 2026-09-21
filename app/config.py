"""Configuration settings for Supermarket Ops Agent."""

import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # App & Telegram
    APP_NAME: str = "Supermarket Ops Agent"
    APP_ENV: str = "development"
    DEBUG: bool = True
    TELEGRAM_BOT_TOKEN: str = ""
    WEBHOOK_URL: Optional[str] = None
    PORT: int = 8000

    # LLM Settings (Universal provider support: OpenAI / Gemini / LiteLLM / Groq / Anthropic / Local)
    LLM_API_KEY: str = ""
    LLM_BASE_URL: Optional[str] = None
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gemini-flash-latest")

    # Database
    DATABASE_URL: str = "sqlite:///./supermarket.db"

    # Shop Defaults
    DEFAULT_SHOP_NAME: str = "Sri Lakshmi Stores"
    DEFAULT_GSTIN: str = "33AAAAA0000A1Z5"
    DEFAULT_SHOP_ADDRESS: str = "12 Bazaar Street, Anna Nagar, Chennai, Tamil Nadu - 600040"
    DEFAULT_SHOP_PHONE: str = "+91 98765 43210"
    DEFAULT_PAYMENT_MODE: str = "UPI"

    # Artifacts Storage
    ARTIFACTS_DIR: str = str(Path(__file__).parent.parent / "generated_artifacts")

    def ensure_artifacts_dir(self) -> Path:
        p = Path(self.ARTIFACTS_DIR)
        p.mkdir(parents=True, exist_ok=True)
        return p


settings = Settings()
