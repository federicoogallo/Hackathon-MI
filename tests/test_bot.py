"""Telegram command handling with all network requests mocked."""

import runpy
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def test_script_initializes_dispatcher_before_processing_updates(tmp_path):
    session = MagicMock()
    session.get.side_effect = [
        MagicMock(status_code=200),
        MagicMock(status_code=200, json=lambda: {"result": [{
            "update_id": 1,
            "message": {"chat": {"id": 123}, "text": "/help"},
        }]}),
        SystemExit,
    ]
    session.post.return_value = MagicMock(status_code=200)

    with (
        patch("requests.Session", return_value=session),
        patch("atexit.register"),
        patch("config.DATA_DIR", tmp_path),
        patch("config.TELEGRAM_BOT_TOKEN", "test-token"),
        patch("config.TELEGRAM_CHAT_ID", "123"),
        patch("config.PUBLIC_SITE_URL", "https://hackathon-milano.vercel.app"),
        pytest.raises(SystemExit),
    ):
        runpy.run_path(str(Path(__file__).parents[1] / "bot.py"), run_name="__main__")

    session.post.assert_called_once()
    text = session.post.call_args.kwargs["json"]["text"]
    assert "https://hackathon-milano.vercel.app" in text
    assert "/scan" in text


def test_manual_scan_uses_pipeline_summary_without_obsolete_followup():
    import bot

    def run_immediately(*, target, daemon):
        return MagicMock(start=target)

    with (
        patch("bot._is_authorized", return_value=True),
        patch("bot._scan_in_progress", False),
        patch("bot._send") as send,
        patch("bot.threading.Thread", side_effect=run_immediately),
        patch("main.run_pipeline") as pipeline,
    ):
        bot._handle_scan(123)

    pipeline.assert_called_once_with(dry_run=False)
    send.assert_called_once()
    assert "Scansione avviata" in send.call_args.args[1]


def test_send_failure_does_not_log_telegram_token(caplog):
    import bot
    import requests

    with patch("bot._session.post", side_effect=requests.ConnectionError(
        "https://api.telegram.org/botprivate-test-token/sendMessage failed"
    )):
        assert bot._send(123, "Test") is False

    assert "ConnectionError" in caplog.text
    assert "private-test-token" not in caplog.text
