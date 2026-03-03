"""
Test suite per notifiers/telegram.py e per la pipeline completa.
"""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from models import HackathonEvent
from notifiers.telegram import (
    _escape_html,
    _send_message,
)
from storage.json_store import EventStore


# =============================================================================
#  Telegram — Escape HTML
# =============================================================================

class TestEscapeHTML:
    def test_ampersand(self):
        assert _escape_html("A & B") == "A &amp; B"

    def test_angle_brackets(self):
        assert _escape_html("<script>alert(1)</script>") == "&lt;script&gt;alert(1)&lt;/script&gt;"

    def test_multiple(self):
        assert _escape_html("a<b&c>d") == "a&lt;b&amp;c&gt;d"

    def test_plain_text(self):
        assert _escape_html("hello world") == "hello world"


# =============================================================================
#  Telegram — Send message
# =============================================================================

class TestSendMessage:
    @patch("notifiers.telegram.config")
    def test_returns_false_without_token(self, mock_config):
        mock_config.TELEGRAM_BOT_TOKEN = ""
        mock_config.TELEGRAM_CHAT_ID = "123"
        assert _send_message("test") is False

    @patch("notifiers.telegram.config")
    def test_returns_false_without_chat_id(self, mock_config):
        mock_config.TELEGRAM_BOT_TOKEN = "token"
        mock_config.TELEGRAM_CHAT_ID = ""
        assert _send_message("test") is False

    @patch("notifiers.telegram.requests.post")
    @patch("notifiers.telegram.config")
    def test_success(self, mock_config, mock_post):
        mock_config.TELEGRAM_BOT_TOKEN = "token"
        mock_config.TELEGRAM_CHAT_ID = "123"
        mock_post.return_value = MagicMock(status_code=200)
        assert _send_message("test") is True
        mock_post.assert_called_once()

    @patch("notifiers.telegram.requests.post")
    @patch("notifiers.telegram.config")
    def test_api_error(self, mock_config, mock_post):
        mock_config.TELEGRAM_BOT_TOKEN = "token"
        mock_config.TELEGRAM_CHAT_ID = "123"
        mock_post.return_value = MagicMock(status_code=400, text="Bad request")
        assert _send_message("test") is False


# =============================================================================
#  Pipeline — Test integrazione
# =============================================================================

class TestPipelineIntegration:
    """Test del flusso pipeline con collector e filtri mockati."""

    @patch("main.llm_filter")
    @patch("main.keyword_filter_batch")
    @patch("main.run_collectors")
    @patch("main.EventStore")
    def test_dry_run_pipeline(
        self, MockStore, mock_run_coll, mock_kw, mock_llm
    ):
        """Pipeline dry-run: nessuna notifica reale."""
        from main import run_pipeline

        # Setup mocks
        store_instance = MagicMock()
        store_instance.count = 0
        store_instance.is_duplicate.return_value = False
        MockStore.return_value = store_instance

        events = [
            HackathonEvent(title="Hack1", url="https://a.com/1", source="s"),
            HackathonEvent(title="Hack2", url="https://a.com/2", source="s"),
        ]
        mock_run_coll.return_value = (events, ["s"], [])
        mock_kw.return_value = (events, 0)
        mock_llm.return_value = (events, 0)

        run_pipeline(dry_run=True)

    def test_dedup_intra_batch(self):
        """Dedup intra-batch: stesso URL da collector diversi → uno solo."""
        from main import deduplicate_against_store

        store = EventStore(path=Path("/tmp/_test_dedup_intra.json"))
        events = [
            HackathonEvent(title="A", url="https://x.com/same", source="s1"),
            HackathonEvent(title="A", url="https://x.com/same", source="s2"),
            HackathonEvent(title="B", url="https://x.com/other", source="s1"),
        ]
        result = deduplicate_against_store(events, store)
        assert len(result) == 2  # same URL deduplicato

    def test_dedup_vs_store(self):
        """Dedup vs store: evento già nello storico → escluso."""
        from main import deduplicate_against_store

        store = EventStore(path=Path("/tmp/_test_dedup_store.json"))
        existing = HackathonEvent(title="Old", url="https://x.com/old", source="s1")
        store.add_event(existing)

        events = [
            HackathonEvent(title="Old", url="https://x.com/old", source="s2"),  # duplicato
            HackathonEvent(title="New", url="https://x.com/new", source="s1"),  # nuovo
        ]
        result = deduplicate_against_store(events, store)
        assert len(result) == 1
        assert result[0].title == "New"
