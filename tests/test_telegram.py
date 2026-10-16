import json

import httpx
import pytest

from pota_bot.telegram import TelegramClient, TelegramError


def client_with(handler):
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return TelegramClient("TOKEN", http=http)


async def test_send_message_posts_expected_payload():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 5}})

    result = await client_with(handler).send_message(42, "ciao", reply_to_message_id=7)
    assert seen["url"] == "https://api.telegram.org/botTOKEN/sendMessage"
    assert seen["body"]["chat_id"] == 42
    assert seen["body"]["text"] == "ciao"
    assert seen["body"]["reply_parameters"] == {"message_id": 7}
    assert seen["body"]["link_preview_options"] == {"is_disabled": True}
    assert result == {"message_id": 5}


async def test_long_text_is_cut_to_telegram_limit():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"ok": True, "result": {}})

    await client_with(handler).send_message(1, "x" * 5000)
    assert len(seen["body"]["text"]) == 4096


async def test_telegram_error_is_raised_with_description():
    def handler(request):
        return httpx.Response(400, json={"ok": False, "description": "Bad Request: chat not found"})

    with pytest.raises(TelegramError, match="chat not found"):
        await client_with(handler).send_message(1, "ciao")
