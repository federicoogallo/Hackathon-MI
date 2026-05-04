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

    @patch("main.generate_readme_table")
    @patch("main.generate_html")
    @patch("main.llm_dedup")
    @patch("main.llm_filter")
    @patch("main.keyword_filter_batch")
    @patch("main.run_collectors")
    @patch("main.EventStore")
    def test_dry_run_pipeline(
        self,
        MockStore,
        mock_run_coll,
        mock_kw,
        mock_llm,
        mock_llm_dedup,
        mock_generate_html,
        mock_generate_readme_table,
        tmp_path,
    ):
        """Pipeline dry-run: nessuna notifica reale e nessun export nel repo."""
        from main import run_pipeline

        # Setup mocks
        store_instance = MagicMock()
        store_instance.count = 0
        store_instance.all_events.return_value = []
        store_instance.is_duplicate.return_value = False
        MockStore.return_value = store_instance

        events = [
            HackathonEvent(title="Hack1", url="https://a.com/1", source="s"),
            HackathonEvent(title="Hack2", url="https://a.com/2", source="s"),
        ]
        collector_runs = [{
            "name": "s",
            "ok": True,
            "event_count": 2,
            "duration_seconds": 0.1,
            "error": "",
        }]
        mock_run_coll.return_value = (events, ["s"], [], collector_runs)
        mock_kw.return_value = (events, 0)
        mock_llm.return_value = (events, 0)
        mock_llm_dedup.return_value = events

        with (
            patch("main.config.DATA_DIR", tmp_path),
            patch("main.config.REVIEW_QUEUE_FILE", tmp_path / "review_queue.json"),
            patch("main.config.REVIEW_DECISIONS_FILE", tmp_path / "review_decisions.json"),
        ):
            run_pipeline(dry_run=True)

        report = json.loads((tmp_path / "last_report.json").read_text())
        assert report["status"] == "completed"
        assert report["collector_runs"] == collector_runs
        assert report["review_queue"] == 0
        review_payload = json.loads((tmp_path / "review_queue.json").read_text())
        assert review_payload["count"] == 0
        mock_llm_dedup.assert_called_once_with(events)
        mock_generate_html.assert_called_once()
        mock_generate_readme_table.assert_called_once()

    @patch("main.generate_readme_table")
    @patch("main.generate_html")
    @patch("main.llm_dedup")
    @patch("main.llm_filter")
    @patch("main.keyword_filter_batch")
    @patch("main.run_collectors")
    @patch("main.EventStore")
    def test_llm_api_error_preserves_store_even_with_few_candidates(
        self,
        MockStore,
        mock_run_coll,
        mock_kw,
        mock_llm,
        mock_llm_dedup,
        mock_generate_html,
        mock_generate_readme_table,
        tmp_path,
    ):
        """Se il LLM fallisce, non salva nuovi eventi ma aggiorna il timestamp scansione."""
        from main import run_pipeline

        store_instance = MagicMock()
        store_instance.count = 0
        store_instance.all_events.return_value = []
        store_instance.is_duplicate.return_value = False
        MockStore.return_value = store_instance

        events = [
            HackathonEvent(title="Hack1", url="https://a.com/1", source="s"),
            HackathonEvent(title="Hack2", url="https://a.com/2", source="s"),
        ]
        collector_runs = [{
            "name": "s",
            "ok": True,
            "event_count": 2,
            "duration_seconds": 0.1,
            "error": "",
        }]
        mock_run_coll.return_value = (events, ["s"], [], collector_runs)
        mock_kw.return_value = (events, 0)
        mock_llm.return_value = ([], len(events))

        with (
            patch("main.config.DATA_DIR", tmp_path),
            patch("main.config.REVIEW_QUEUE_FILE", tmp_path / "review_queue.json"),
            patch("main.config.REVIEW_DECISIONS_FILE", tmp_path / "review_decisions.json"),
        ):
            run_pipeline(dry_run=True)

        report = json.loads((tmp_path / "last_report.json").read_text())
        assert report["status"] == "llm_failed_preserved"
        assert report["collector_runs"] == collector_runs
        assert report["review_queue"] == 0
        mock_llm_dedup.assert_not_called()
        store_instance.add_event.assert_not_called()
        store_instance.save_with_timestamp.assert_not_called()
        store_instance.touch_last_check.assert_called_once()
        mock_generate_html.assert_called_once()
        mock_generate_readme_table.assert_called_once()

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

    def test_post_llm_dedup_vs_store_with_extracted_date(self):
        """Dedup post-LLM: con data estratta deve bloccare duplicati contro lo storico."""
        from main import deduplicate_post_llm_against_store

        store = EventStore(path=Path("/tmp/_test_post_llm_dedup_store.json"))
        existing = HackathonEvent(
            title="Il Wikimedia Hackathon 2026 arriva a Milano - Wikimedia Italia",
            url="https://www.wikimedia.it/news/il-wikimedia-hackathon-2026-arriva-a-milano/",
            source="web_search",
            description="Wikimedia Hackathon a Milano dal 1 al 3 maggio 2026",
            date_str="2026-05-01",
            location="Milano",
        )
        store.add_event(existing)

        candidate = HackathonEvent(
            title="2026 Wikimedia Hackathon",
            url="https://lists.wikimedia.org/hyperkitty/list/wikimedia-l@example/message/abc/",
            source="web_search",
            description="The 2026 Wikimedia Hackathon will take place in Milan on May 1-3, 2026",
            date_str="2026-05-01",
            location="Milano",
        )

        result = deduplicate_post_llm_against_store([candidate], store)
        assert result == []


class TestPipelineQualityGate:
    def test_rejects_blacklisted_event(self, tmp_path):
        from main import _passes_quality_gate

        blacklist = tmp_path / "blacklist.txt"
        blacklist.write_text("python coding challenge\n", encoding="utf-8")

        ev = HackathonEvent(
            title="Python Coding Challenge",
            url="https://example.com/python-challenge",
            source="web_search",
            description="Question with answer",
            location="Milano",
        )

        with patch("main.config.BLACKLIST_FILE", blacklist):
            ok, reason = _passes_quality_gate(ev)

        assert ok is False
        assert "blacklist" in reason

    def test_rejects_non_milan_event_with_explicit_location(self):
        from main import _passes_quality_gate

        ev = HackathonEvent(
            title="Hackaday Europe 2026",
            url="https://www.eventbrite.com/e/hackaday-europe-2026",
            source="eventbrite_web",
            location="1/c Via Gaetano Previati, Lecco",
            description="Hardware event in Lecco",
        )
        ok, reason = _passes_quality_gate(ev)
        assert ok is False
        assert "Milano" in reason or "non a Milano" in reason

    def test_rejects_clearly_past_event(self):
        from main import _passes_quality_gate

        ev = HackathonEvent(
            title="AssoSoftware organizza il primo Hackathon dedicato all'IA",
            url="https://polihub.it/news-it/assosoftware-hackathon-2024/",
            source="web_search",
            description="Evento del 2024",
        )
        ok, reason = _passes_quality_gate(ev)
        assert ok is False
        assert "passato" in reason

    def test_fallback_semantic_dedup_removes_wikimedia_duplicate(self):
        from main import _deterministic_semantic_dedup

        a = HackathonEvent(
            title="Il Wikimedia Hackathon 2026 arriva a Milano - Wikimedia Italia",
            url="https://www.wikimedia.it/news/il-wikimedia-hackathon-2026-arriva-a-milano/",
            source="web_search",
            description="Wikimedia Hackathon a Milano dal 1 al 3 maggio 2026",
            date_str="2026-05-01",
            location="Milano",
        )
        b = HackathonEvent(
            title="[Wikitech-l] Reminder: Registration for the 2026 Wikimedia ...",
            url="https://lists.wikimedia.org/hyperkitty/list/wikitech-l@example/message/abc/",
            source="web_search",
            description="The 2026 Wikimedia Hackathon will be taking place in Milan on May 1-3, 2026",
            date_str="2026-05-01",
            location="Milano",
        )

        out = _deterministic_semantic_dedup([a, b])
        assert len(out) == 1
        assert "wikimedia.it" in out[0].url

    def test_rejects_known_false_positive_urls(self):
        from main import _passes_quality_gate

        ev1 = HackathonEvent(
            title="Hack the agriculture! | [hackathon]",
            url="https://www.eventbrite.it/e/biglietti-hack-the-agriculture-hackathon-1984749196274",
            source="web_search",
        )
        ev2 = HackathonEvent(
            title="AssoSoftware organizza il primo Hackathon dedicato all'IA nei",
            url="https://polihub.it/news-it/assosoftware-organizza-il-primo-hackathon-su-scala-nazionale-dedicato-allia-nei-software-gestionali/",
            source="web_search",
        )

        ok1, _ = _passes_quality_gate(ev1)
        ok2, _ = _passes_quality_gate(ev2)
        assert ok1 is False
        assert ok2 is False

    def test_rejects_undated_stale_web_result(self):
        from main import _passes_quality_gate

        ev = HackathonEvent(
            title="Hacking the City",
            url="https://hackingthecity.today/",
            source="web_search",
            description="L'Hackathon è stato pensato per far nascere progettualità nelle città.",
            location="",
            date_str="",
        )

        ok, reason = _passes_quality_gate(ev)
        assert ok is False
        assert "senza data" in reason or "passato" in reason
