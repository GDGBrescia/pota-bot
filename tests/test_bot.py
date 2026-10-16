import pytest

from pota_bot.bot import ERROR_TEXT, PRIVACY_TEXT, RATE_LIMIT_TEXT, PotaBot, clean_text, is_addressed_to_bot
from pota_bot.ratelimit import RateLimiter

BOT = "pota_test_bot"


def message(text, chat_type="group", reply_to_username=None, user_id=10):
    msg = {"message_id": 99, "text": text, "chat": {"id": -100, "type": chat_type}, "from": {"id": user_id}}
    if reply_to_username:
        msg["reply_to_message"] = {"from": {"username": reply_to_username, "is_bot": True}}
    return {"update_id": 1, "message": msg}


class FakeTelegram:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, reply_to_message_id=None):
        self.sent.append((chat_id, text, reply_to_message_id))


class FakeAsk:
    def __init__(self, reply="risposta", error=None):
        self.questions = []
        self.reply, self.error = reply, error

    async def __call__(self, user_id, session_id, text):
        self.questions.append((user_id, session_id, text))
        if self.error:
            raise self.error
        return self.reply


def make_bot(ask=None, limit=20):
    telegram = FakeTelegram()
    bot = PotaBot(telegram=telegram, ask=ask or FakeAsk(), bot_username=BOT, limiter=RateLimiter(limit))
    return bot, telegram


@pytest.mark.parametrize("msg,expected", [
    (message("ciao", chat_type="private")["message"], True),
    (message("ciao a tutti")["message"], False),
    (message("@Pota_Test_Bot quando è il prossimo evento?")["message"], True),
    (message("e quindi?", reply_to_username=BOT)["message"], True),
    (message("e quindi?", reply_to_username="altro_bot")["message"], False),
])
def test_is_addressed_to_bot(msg, expected):
    assert is_addressed_to_bot(msg, BOT) is expected


def test_clean_text_removes_mention():
    assert clean_text("@pota_test_bot  quando è il prossimo evento?", BOT) == "quando è il prossimo evento?"


async def test_group_message_without_mention_is_ignored():
    bot, telegram = make_bot()
    await bot.handle_update(message("ciao a tutti"))
    assert telegram.sent == []


async def test_mention_gets_answer_as_reply():
    ask = FakeAsk(reply="Il 12 novembre!")
    bot, telegram = make_bot(ask)
    await bot.handle_update(message(f"@{BOT} prossimo evento?"))
    assert ask.questions == [("10", "-100:10", "prossimo evento?")]
    assert telegram.sent == [(-100, "Il 12 novembre!", 99)]


async def test_privacy_command_works_with_bot_suffix():
    bot, telegram = make_bot()
    await bot.handle_update(message(f"/privacy@{BOT}"))
    assert telegram.sent[0][1] == PRIVACY_TEXT


async def test_unknown_command_is_ignored():
    bot, telegram = make_bot()
    await bot.handle_update(message("/sconosciuto"))
    assert telegram.sent == []


async def test_rate_limit_stops_the_agent():
    ask = FakeAsk()
    bot, telegram = make_bot(ask, limit=1)
    await bot.handle_update(message("ciao", chat_type="private"))
    await bot.handle_update(message("ancora", chat_type="private"))
    assert len(ask.questions) == 1
    assert telegram.sent[-1][1] == RATE_LIMIT_TEXT


async def test_agent_error_becomes_friendly_message():
    bot, telegram = make_bot(FakeAsk(error=RuntimeError("quota")))
    await bot.handle_update(message("ciao", chat_type="private"))
    assert telegram.sent[-1][1] == ERROR_TEXT


async def test_updates_without_text_are_ignored():
    bot, telegram = make_bot()
    await bot.handle_update({"update_id": 1, "message": {"message_id": 1, "chat": {"id": 1, "type": "private"}}})
    await bot.handle_update({"update_id": 2, "edited_message": {}})
    assert telegram.sent == []
