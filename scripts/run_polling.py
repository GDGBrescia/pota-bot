"""Pota Bot in locale, senza cloud: legge i messaggi con il polling.

Uso:
  .venv/bin/python scripts/run_polling.py            # il bot risponde su Telegram
  .venv/bin/python scripts/run_polling.py --digest   # genera il digest e lo manda a TELEGRAM_DIGEST_CHAT_ID
"""
import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / "pota_bot" / ".env")

from pota_bot.agent import build_agent  # noqa: E402
from pota_bot.bot import PotaBot  # noqa: E402
from pota_bot.chat import AgentChat  # noqa: E402
from pota_bot.digest import build_weekly_digest, gemini_generate  # noqa: E402
from pota_bot.ratelimit import RateLimiter  # noqa: E402
from pota_bot.storage import MemoryProposalStore  # noqa: E402
from pota_bot.telegram import TelegramClient  # noqa: E402

logging.basicConfig(level=logging.INFO)
# httpx scriverebbe nei log l'URL completo, che per Telegram contiene il token del bot.
logging.getLogger("httpx").setLevel(logging.WARNING)


async def run_bot(telegram: TelegramClient) -> None:
    bot = PotaBot(telegram, AgentChat(build_agent(MemoryProposalStore())).ask,
                  os.environ["TELEGRAM_BOT_USERNAME"], RateLimiter(20))
    await telegram.delete_webhook()  # il polling non funziona se c'è un webhook attivo
    print("✅ Pota Bot in ascolto. Scrivigli su Telegram (Ctrl+C per fermare).")
    offset = 0
    while True:
        for update in await telegram.get_updates(offset=offset):
            offset = update["update_id"] + 1
            chat = (update.get("message") or {}).get("chat") or {}
            print(f"📨 chat {chat.get('id')} ({chat.get('type')}): {(update.get('message') or {}).get('text')}")
            await bot.handle_update(update)


async def send_digest(telegram: TelegramClient) -> None:
    text = await build_weekly_digest(gemini_generate)
    print(text or "(nessuna notizia questa settimana)")
    chat_id = os.environ.get("TELEGRAM_DIGEST_CHAT_ID")
    if text and chat_id:
        await telegram.send_message(chat_id, text)
        print(f"✅ Digest inviato alla chat {chat_id}")


async def main() -> None:
    client = TelegramClient(os.environ["TELEGRAM_BOT_TOKEN"])
    try:
        await (send_digest(client) if "--digest" in sys.argv else run_bot(client))
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
