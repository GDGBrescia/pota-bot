from pota_bot.agent import root_agent


def test_root_agent_loads():
    assert root_agent.name == "pota_bot"


def test_default_model_retries_only_temporary_errors():
    retry = root_agent.model.retry_options
    assert retry.attempts == 4
    assert 503 in retry.http_status_codes and 429 not in retry.http_status_codes
