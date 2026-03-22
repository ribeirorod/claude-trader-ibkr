import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_update(chat_id: str, text: str = "hello") -> MagicMock:
    update = MagicMock()
    update.effective_chat.id = int(chat_id)
    update.effective_user.id = int(chat_id)
    update.effective_user.username = None
    update.message.text = text
    update.message.voice = None
    update.message.document = None
    update.message.photo = None
    update.message.caption = None
    update.message.reply_text = AsyncMock()
    update.message.reply_markdown = AsyncMock()
    return update


def test_build_telegram_app_returns_application(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:ABC")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "456")
    from trader.server.telegram import build_telegram_app
    app = build_telegram_app()
    assert app is not None


@pytest.mark.asyncio
async def test_unauthorized_message_is_ignored(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:ABC")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "456")
    from trader.server.telegram import _handle_message

    update = _make_update(chat_id="999", text="intruder")
    ctx = MagicMock()

    with patch("trader.server.telegram.agent.ask", new_callable=AsyncMock) as mock_ask:
        await _handle_message(update, ctx)
        mock_ask.assert_not_called()


@pytest.mark.asyncio
async def test_authorized_message_dispatches_to_agent(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:ABC")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "456")
    from trader.server.telegram import _handle_message

    update = _make_update(chat_id="456", text="show positions")
    ctx = MagicMock()

    with patch("trader.server.telegram.agent.ask", new_callable=AsyncMock, return_value="AAPL: 10 shares") as mock_ask:
        with patch("trader.server.telegram._send_response", new_callable=AsyncMock):
            await _handle_message(update, ctx)
            mock_ask.assert_called_once()
            # text is the first positional arg to agent.ask(text, chat_id=...)
            assert mock_ask.call_args.args[0] == "show positions"
