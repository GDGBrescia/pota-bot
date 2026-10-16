"""Le poche chiamate alla Bot API di Telegram che ci servono, con httpx."""
import httpx

API_URL = "https://api.telegram.org"
MAX_TEXT = 4096


class TelegramError(RuntimeError):
    pass


class TelegramClient:
    def __init__(self, token: str, http: httpx.AsyncClient | None = None):
        self._base = f"{API_URL}/bot{token}"
        self._http = http or httpx.AsyncClient(timeout=45)

    async def _call(self, method: str, **payload):
        response = await self._http.post(f"{self._base}/{method}", json=payload)
        data = response.json()
        if not data.get("ok"):
            raise TelegramError(data.get("description", f"errore Telegram {response.status_code}"))
        return data["result"]

    async def send_message(self, chat_id, text: str, reply_to_message_id: int | None = None):
        payload = {"chat_id": chat_id, "text": text[:MAX_TEXT], "link_preview_options": {"is_disabled": True}}
        if reply_to_message_id is not None:
            payload["reply_parameters"] = {"message_id": reply_to_message_id}
        return await self._call("sendMessage", **payload)

    async def set_webhook(self, url: str, secret_token: str):
        return await self._call("setWebhook", url=url, secret_token=secret_token, allowed_updates=["message"])

    async def delete_webhook(self):
        return await self._call("deleteWebhook")

    async def get_updates(self, offset: int, timeout: int = 30):
        return await self._call("getUpdates", offset=offset, timeout=timeout, allowed_updates=["message"])
