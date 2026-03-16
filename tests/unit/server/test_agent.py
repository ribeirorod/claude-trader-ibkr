import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_ask_returns_text_from_assistant_message():
    from claude_agent_sdk import AssistantMessage, TextBlock
    from trader.server.agent import ask

    # Use spec= so isinstance() checks in the real code work correctly
    mock_text_block = MagicMock(spec=TextBlock)
    mock_text_block.text = "AAPL is at $200"

    mock_assistant = MagicMock(spec=AssistantMessage)
    mock_assistant.content = [mock_text_block]

    async def fake_query(prompt, options):
        yield mock_assistant

    with patch("trader.server.agent.query", fake_query):
        result = await ask("What is AAPL?", chat_id="123")

    assert result == "AAPL is at $200"


@pytest.mark.asyncio
async def test_ask_raises_on_error_result():
    from claude_agent_sdk import ResultMessage
    from trader.server.agent import ask

    mock_result = MagicMock(spec=ResultMessage)
    mock_result.is_error = True
    mock_result.__str__ = lambda self: "tool error"

    async def fake_query(prompt, options):
        yield mock_result

    with patch("trader.server.agent.query", fake_query):
        with pytest.raises(RuntimeError, match="tool error"):
            await ask("bad request", chat_id="123")


@pytest.mark.asyncio
async def test_run_job_does_not_raise_on_success():
    from claude_agent_sdk import ResultMessage
    from trader.server.agent import run_job

    mock_result = MagicMock(spec=ResultMessage)
    mock_result.is_error = False
    mock_result.result = "done"

    async def fake_query(prompt, options):
        yield mock_result

    with patch("trader.server.agent.query", fake_query):
        # Should complete without raising
        await run_job("Run eu-pre-market analysis", slot="eu-pre-market")
