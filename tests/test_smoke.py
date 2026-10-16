from pota_bot.agent import root_agent


def test_root_agent_loads():
    assert root_agent.name == "pota_bot"
