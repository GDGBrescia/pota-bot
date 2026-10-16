"""Gli endpoint del servizio. `create_app` riceve i pezzi già pronti, così si testa senza cloud."""
import logging
import secrets
from typing import Awaitable, Callable

from fastapi import FastAPI, Header, HTTPException, Request

from pota_bot.config import Settings

logging.basicConfig(level=logging.INFO)


def _same_secret(given: str | None, expected: str) -> bool:
    return bool(expected) and secrets.compare_digest(given or "", expected)


def create_app(bot, settings: Settings, digest_job: Callable[[], Awaitable[str]]) -> FastAPI:
    app = FastAPI(title="Pota Bot")

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    @app.post("/telegram/webhook")
    async def telegram_webhook(request: Request,
                               x_telegram_bot_api_secret_token: str | None = Header(default=None)):
        if not _same_secret(x_telegram_bot_api_secret_token, settings.telegram_webhook_secret):
            raise HTTPException(status_code=403)
        # La risposta si genera PRIMA di restituire 200: su Cloud Run, dopo la risposta la CPU viene ridotta.
        await bot.handle_update(await request.json())
        return {"ok": True}

    @app.post("/tasks/digest")
    async def weekly_digest(x_pota_task_token: str | None = Header(default=None)):
        if not _same_secret(x_pota_task_token, settings.task_token):
            raise HTTPException(status_code=403)
        text = await digest_job()
        return {"ok": True, "chars": len(text)}

    return app
