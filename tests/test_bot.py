import pytest

from pota_bot.bot import EMPTY_TEXT, ERROR_TEXT, PRIVACY_TEXT, RATE_LIMIT_TEXT, PotaBot, clean_text, is_addressed_to_bot
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
    (message("@pota_test_bot_2 ciao")["message"], False),
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


async def test_command_for_another_bot_is_ignored():
    bot, telegram = make_bot()
    await bot.handle_update(message("/help@altro_bot"))
    assert telegram.sent == []


async def test_path_like_text_is_not_a_command():
    ask = FakeAsk(reply="È un percorso.")
    bot, telegram = make_bot(ask)
    await bot.handle_update(message(f"/etc/hosts cos'è? @{BOT}"))
    assert len(ask.questions) == 1
    assert telegram.sent[-1][1] == "È un percorso."


async def test_failed_send_does_not_escape_handle_update():
    class FailingTelegram:
        async def send_message(self, chat_id, text, reply_to_message_id=None):
            raise RuntimeError("telegram giù")

    bot = PotaBot(telegram=FailingTelegram(), ask=FakeAsk(), bot_username=BOT, limiter=RateLimiter(20))
    await bot.handle_update(message("ciao", chat_type="private"))


async def test_empty_question_does_not_consume_rate_limit():
    ask = FakeAsk()
    bot, telegram = make_bot(ask, limit=1)
    await bot.handle_update(message(f"@{BOT}"))
    await bot.handle_update(message(f"@{BOT} ciao"))
    assert len(ask.questions) == 1
    assert telegram.sent[-1][1] == "risposta"


async def test_chiedi_in_group_asks_with_cleaned_question():
    ask = FakeAsk(reply="Il 12 novembre!")
    bot, telegram = make_bot(ask)
    await bot.handle_update(message("/chiedi quando è il prossimo evento?"))
    assert ask.questions == [("10", "-100:10", "quando è il prossimo evento?")]
    assert telegram.sent == [(-100, "Il 12 novembre!", 99)]


async def test_chiedi_with_our_bot_suffix_is_answered():
    ask = FakeAsk()
    bot, telegram = make_bot(ask)
    await bot.handle_update(message(f"/chiedi@{BOT} domanda"))
    assert ask.questions == [("10", "-100:10", "domanda")]
    assert telegram.sent[-1][1] == "risposta"


async def test_chiedi_for_another_bot_is_ignored():
    ask = FakeAsk()
    bot, telegram = make_bot(ask)
    await bot.handle_update(message("/chiedi@altro_bot domanda"))
    assert ask.questions == []
    assert telegram.sent == []


async def test_chiedi_works_in_private_chat():
    ask = FakeAsk()
    bot, telegram = make_bot(ask)
    await bot.handle_update(message("/chiedi ciao", chat_type="private"))
    assert ask.questions == [("10", "-100:10", "ciao")]


async def test_chiedi_without_question_gets_empty_text_and_keeps_rate_limit():
    ask = FakeAsk()
    bot, telegram = make_bot(ask, limit=1)
    await bot.handle_update(message("/chiedi"))
    await bot.handle_update(message(f"/chiedi@{BOT}   "))
    assert ask.questions == []
    assert [s[1] for s in telegram.sent] == [EMPTY_TEXT, EMPTY_TEXT]
    await bot.handle_update(message("/chiedi ora sì"))
    assert len(ask.questions) == 1


async def test_chiedi_is_rate_limited():
    ask = FakeAsk()
    bot, telegram = make_bot(ask, limit=1)
    await bot.handle_update(message("/chiedi uno"))
    await bot.handle_update(message("/chiedi due"))
    assert len(ask.questions) == 1
    assert telegram.sent[-1][1] == RATE_LIMIT_TEXT


async def test_chiedi_agent_error_becomes_friendly_message():
    bot, telegram = make_bot(FakeAsk(error=RuntimeError("quota")))
    await bot.handle_update(message("/chiedi ciao"))
    assert telegram.sent[-1][1] == ERROR_TEXT
