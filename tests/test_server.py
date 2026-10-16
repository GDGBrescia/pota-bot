from fastapi.testclient import TestClient

from pota_bot.config import Settings
from server.main import create_app

SETTINGS = Settings(
    telegram_bot_token="T", telegram_bot_username="pota_test_bot", telegram_webhook_secret="segreto",
    task_token="task", digest_chat_id="-100", use_firestore=False, rate_limit_per_hour=20,
)


class FakeBot:
    def __init__(self):
        self.updates = []

    async def handle_update(self, update):
        self.updates.append(update)


def make_client():
    bot, digests = FakeBot(), []

    async def digest_job():
        digests.append(True)
        return "digest"

    return TestClient(create_app(bot, SETTINGS, digest_job)), bot, digests


def test_healthz():
    client, _, _ = make_client()
    assert client.get("/healthz").json() == {"ok": True}


def test_webhook_rejects_wrong_secret():
    client, bot, _ = make_client()
    r = client.post("/telegram/webhook", json={"update_id": 1}, headers={"X-Telegram-Bot-Api-Secret-Token": "no"})
    assert r.status_code == 403 and bot.updates == []


def test_webhook_passes_update_to_bot():
    client, bot, _ = make_client()
    r = client.post("/telegram/webhook", json={"update_id": 1}, headers={"X-Telegram-Bot-Api-Secret-Token": "segreto"})
    assert r.status_code == 200 and bot.updates == [{"update_id": 1}]


def test_digest_needs_task_token():
    client, _, digests = make_client()
    assert client.post("/tasks/digest").status_code == 403
    r = client.post("/tasks/digest", headers={"X-Pota-Task-Token": "task"})
    assert r.status_code == 200 and digests == [True]


def test_empty_secret_in_config_rejects_everything():
    from dataclasses import replace
    bot = FakeBot()

    async def digest_job():
        return ""

    client = TestClient(create_app(bot, replace(SETTINGS, telegram_webhook_secret=""), digest_job))
    r = client.post("/telegram/webhook", json={}, headers={"X-Telegram-Bot-Api-Secret-Token": ""})
    assert r.status_code == 403
