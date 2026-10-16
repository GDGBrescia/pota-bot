"""Configurazione del servizio, letta dalle variabili d'ambiente."""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    telegram_bot_username: str
    telegram_webhook_secret: str
    task_token: str
    digest_chat_id: str
    use_firestore: bool
    rate_limit_per_hour: int

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            telegram_bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
            telegram_bot_username=os.environ["TELEGRAM_BOT_USERNAME"].lstrip("@"),
            telegram_webhook_secret=os.environ.get("TELEGRAM_WEBHOOK_SECRET", ""),
            task_token=os.environ.get("POTA_TASK_TOKEN", ""),
            digest_chat_id=os.environ.get("TELEGRAM_DIGEST_CHAT_ID", ""),
            use_firestore=os.environ.get("POTA_USE_FIRESTORE", "false").lower() == "true",
            rate_limit_per_hour=int(os.environ.get("POTA_RATE_LIMIT_PER_HOUR", "20")),
        )
