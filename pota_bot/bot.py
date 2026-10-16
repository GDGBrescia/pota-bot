"""Il bot Telegram: decide se un messaggio è per noi, gestisce comandi e limiti, chiede all'agente."""
import logging
import re
from typing import Awaitable, Callable

from .ratelimit import RateLimiter

logger = logging.getLogger(__name__)

Ask = Callable[[str, str, str], Awaitable[str]]

HELP_TEXT = (
    "Pota! Sono Pota Bot, il bot di GDG Brescia.\n"
    "Nei gruppi menzionami o rispondi a un mio messaggio: chiedimi degli eventi, delle FAQ, "
    "delle novità su AI e Google, o proponi un tema per i prossimi eventi.\n"
    "/privacy per sapere come uso i messaggi."
)
PRIVACY_TEXT = (
    "I messaggi che mi scrivi vengono elaborati da Gemini (Google) per risponderti. "
    "Non scrivermi dati personali come email, telefono o indirizzi. "
    "Le proposte di temi vengono salvate senza il tuo nome. "
    "Il mio codice è aperto: github.com/GDGBrescia/pota-bot"
)
RATE_LIMIT_TEXT = "Pota, per quest'ora hai già fatto tante domande! Riprova più tardi."
ERROR_TEXT = "Pota, qualcosa è andato storto. Riprova tra un minuto."
EMPTY_TEXT = "Dimmi pure! Chiedimi degli eventi, delle FAQ o delle novità su AI e Google."

COMMANDS = {"/start": HELP_TEXT, "/help": HELP_TEXT, "/privacy": PRIVACY_TEXT}


def command_of(text: str) -> str | None:
    """"/privacy@pota_bot ciao" → "/privacy"; testo normale → None."""
    if not text.startswith("/"):
        return None
    return text.split()[0].split("@")[0].lower()


def is_addressed_to_bot(message: dict, bot_username: str) -> bool:
    if message.get("chat", {}).get("type") == "private":
        return True
    replied_to = (message.get("reply_to_message") or {}).get("from") or {}
    if replied_to.get("username", "").lower() == bot_username.lower():
        return True
    return f"@{bot_username.lower()}" in (message.get("text") or "").lower()


def clean_text(text: str, bot_username: str) -> str:
    return re.sub(rf"@{re.escape(bot_username)}\b", "", text, flags=re.IGNORECASE).strip()


class PotaBot:
    def __init__(self, telegram, ask: Ask, bot_username: str, limiter: RateLimiter):
        self.telegram = telegram
        self.ask = ask
        self.bot_username = bot_username.lstrip("@")
        self.limiter = limiter

    async def handle_update(self, update: dict) -> None:
        message = update.get("message")
        if not message or not message.get("text"):
            return
        chat_id = message["chat"]["id"]
        user_id = str((message.get("from") or {}).get("id", chat_id))
        reply_to = message.get("message_id")
        text = message["text"]

        command = command_of(text)
        if command is not None:
            if command in COMMANDS:
                await self.telegram.send_message(chat_id, COMMANDS[command], reply_to_message_id=reply_to)
            return

        if not is_addressed_to_bot(message, self.bot_username):
            return
        if not self.limiter.allow(user_id):
            await self.telegram.send_message(chat_id, RATE_LIMIT_TEXT, reply_to_message_id=reply_to)
            return

        question = clean_text(text, self.bot_username)
        if not question:
            await self.telegram.send_message(chat_id, EMPTY_TEXT, reply_to_message_id=reply_to)
            return

        try:
            reply = await self.ask(user_id, f"{chat_id}:{user_id}", question)
        except Exception:
            logger.exception("Errore dell'agente sul messaggio %s", reply_to)
            reply = ERROR_TEXT
        await self.telegram.send_message(chat_id, reply or ERROR_TEXT, reply_to_message_id=reply_to)
