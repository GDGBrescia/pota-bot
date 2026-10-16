"""Collega i pezzi veri. Avvio: uvicorn server.production:app"""
import logging

from pota_bot.agent import build_agent
from pota_bot.bot import PotaBot
from pota_bot.chat import AgentChat
from pota_bot.config import Settings
from pota_bot.digest import build_weekly_digest, gemini_generate
from pota_bot.ratelimit import RateLimiter
from pota_bot.storage import FirestoreProposalStore, MemoryProposalStore
from pota_bot.telegram import TelegramClient
from server.main import create_app

settings = Settings.from_env()
if not settings.telegram_webhook_secret or not settings.task_token:
    logging.warning("TELEGRAM_WEBHOOK_SECRET o POTA_TASK_TOKEN vuoto: tutte le richieste riceveranno 403")
store = FirestoreProposalStore() if settings.use_firestore else MemoryProposalStore()
telegram = TelegramClient(settings.telegram_bot_token)
bot = PotaBot(
    telegram=telegram,
    ask=AgentChat(build_agent(store)).ask,
    bot_username=settings.telegram_bot_username,
    limiter=RateLimiter(settings.rate_limit_per_hour),
)


async def digest_job() -> str:
    text = await build_weekly_digest(gemini_generate)
    if text and settings.digest_chat_id:
        await telegram.send_message(settings.digest_chat_id, text)
    return text


app = create_app(bot, settings, digest_job)
