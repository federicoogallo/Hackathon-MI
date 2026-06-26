"""
Test suite per notifiers/telegram.py e per la pipeline completa.
"""

import json
from datetime import date
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

    def test_rejects_foreign_venue_even_if_title_mentions_milan(self):
        from main import _passes_quality_gate

        ev = HackathonEvent(
            title="Milan AI Hackathon meetup edition",
            url="https://example.com/milan-ai",
            source="meetup",
            description="Build AI tools with the community.",
            location="New York, NY, USA",
        )

        ok, reason = _passes_quality_gate(ev)
        assert ok is False
        assert "Milano" in reason or "non a Milano" in reason

    def test_rejects_meetup_event_with_foreign_group_and_derived_milan_location(self):
        from main import _passes_quality_gate

        ev = HackathonEvent(
            title=(
                "Google I/O Build with AI Hackathon x Google Cloud Labs - Day II"
                "Fri, May 22 · 9:00 AM EDTby Google Developer Group (GDG) NYC"
            ),
            url="https://www.meetup.com/gdgnyc/events/314635492/",
            source="meetup",
            location="Milano",
            description="",
        )

        ok, reason = _passes_quality_gate(ev)
        assert ok is False
        assert "Meetup" in reason or "non milanesi" in reason

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

    @pytest.mark.parametrize("title,url", [
        ("Hack-in-Towers", "https://www.bo-om.it/eb_aziende/"),
        ("HACKATHON - ISSA PULIRE", "https://www.issapulire.com/it/eventi/hackathon.html"),
        ("AI Creative Hackathon Vol.1 · Luma", "https://lu.ma/AiCreativeHackathon"),
        ("AI Creative Hackathon Vol.2", "https://lu.ma/wow6yhnn"),
        ("Ideathon - Civil Week Vivere", "https://civilweek-vivere.it/eventi/ideathon-2/"),
        ("Milan Global Game Jam 2026", "https://globalgamejam.it/milano"),
        (
            "Milan Global Game Jam 2026 - IGDA Milan @ SAE Institute",
            "https://globalgamejam.org/jam-sites/2026/milan-global-game-jam-2026-igda-milan-sae-institute",
        ),
        ("EcoHackathon 2026", "https://esp.unimi.it/it/eventi/ecohackathon-2026"),
        ("Global Game Jam", "https://zero.eu/en/eventi/136252-global-game-jam-4,milano/"),
        ("Community Hackathon by CA", "https://levillagebyca.it/it/community-hackathon-by-ca/"),
        ("FastwebAI Hackathon a Milano", "https://www.fastweb.it/fastwebai-hackathon/"),
        (
            "FastwebAI Hackathon: ultimi giorni per candidarti!",
            "https://www.instagram.com/reel/DNne53iIqc2/",
        ),
        ("171 - Beyond Code: The Spec-Driven Development Paradigm", "https://eventitech.it/events/2531"),
        (
            "Raspberry JAM @ Wikimedia Hackathon Milan 2026",
            "https://events.raspberrypi.com/community/6f41b7d6-d731-4376-acf5-c5b5dddb038c",
        ),
        (
            "Event:Hardware tools for Wiki/Raspberry JAM at Wikimedia",
            "https://meta.wikimedia.org/wiki/Event:Hardware_tools_for_Wiki/Raspberry_JAM_at_Wikimedia_Hackathon_Milan_2026",
        ),
        (
            "Hack-AI-thon 2026 - 24 ore di creativita, innovazione e Intelligenza",
            "https://www.instagram.com/p/DVskHCnDZO4/",
        ),
    ])
    def test_rejects_user_reported_false_positive_urls(self, title, url):
        from main import _passes_quality_gate

        ev = HackathonEvent(
            title=title,
            url=url,
            source="web_search",
            description="Milano 2026",
            date_str="",
            location="Milano",
        )

        ok, reason = _passes_quality_gate(ev)
        assert ok is False
        assert "false positive" in reason

    @pytest.mark.parametrize("title,url", [
        ("2026 Quantum HACKday Milano", "https://luma.com/k73gcr0t"),
        (
            "Milan Critical Care Datathon and ESICM's Big Datatalk",
            "https://healthmanagement.org/c/icu/event/milan-critical-care-datathon-and-esicm-s-big-datatalk",
        ),
        ("LUMEN - Creativity, AI and Community", "https://lu.ma/ayybpg05"),
    ])
    def test_rejects_user_reported_stale_undated_web_urls(self, title, url):
        from main import _passes_quality_gate

        ev = HackathonEvent(
            title=title,
            url=url,
            source="web_search",
            description="Milano AI hackathon page without a trustworthy current date.",
            date_str="",
            location="Milano",
        )

        ok, reason = _passes_quality_gate(ev)
        assert ok is False
        assert "senza data" in reason or "passato" in reason

    def test_rejects_known_duplicate_bcg_registration_page(self):
        from main import _passes_quality_gate

        ev = HackathonEvent(
            title="BCG Platinion Hackathon 2026 - Milano | Eightfold",
            url="https://experiencedtalent.bcg.com/events/candidate/registration?plannedEventId=aQnm026Vg",
            source="web_search",
            description=(
                "BCG Platinion Hackathon registration page for the same October 16-17, "
                "2026 event already represented by the official BCG Platinion page."
            ),
            date_str="",
            location="Milano",
        )

        ok, reason = _passes_quality_gate(ev)
        assert ok is False
        assert "duplicato" in reason

    def test_rejects_ctf_as_not_hackathon_format(self):
        from filters.keyword_filter import keyword_filter

        ev = HackathonEvent(
            title="HACK-IN-TOWERS CTF challenge 2026",
            url="https://example.com/ctf",
            source="web_search",
            description="Capture the flag cybersecurity competition in Milano.",
            date_str="2026-11-25",
            location="Milano",
        )

        assert keyword_filter(ev) is False

    def test_rejects_jug_milano_talk(self):
        from filters.keyword_filter import keyword_filter

        ev = HackathonEvent(
            title="JUG Milano - Java User Group talk",
            url="https://example.com/jug-milano",
            source="web_search",
            description="Talk tecnico e networking community, non una sfida di building.",
            date_str="2026-06-10",
            location="Milano",
        )

        assert keyword_filter(ev) is False

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

    def test_rejects_generic_undated_web_search_result(self):
        from main import _passes_quality_gate

        ev = HackathonEvent(
            title="AI Creative Hackathon",
            url="https://aicreativehackathon.com/",
            source="web_search",
            description="AI Creative Hackathon is an event in Milan with competition, talk and music.",
            location="Milano",
            date_str="",
        )

        ok, reason = _passes_quality_gate(ev)
        assert ok is False
        assert "senza data" in reason

    def test_rejects_online_itch_game_jam(self):
        from main import _passes_quality_gate

        ev = HackathonEvent(
            title="GameDev.tv Game Jam 2026",
            url="https://itch.io/jam/gamedevtv-jam-2026",
            source="web_search",
            description=(
                "A game jam from 2026-05-15 to 2026-06-01 hosted by gamedevtv. "
                "Submit a playable web build and join the community online."
            ),
            date_str="2026-05-15",
            location="",
        )

        ok, reason = _passes_quality_gate(ev)
        assert ok is False
        assert "online" in reason

    def test_rejects_tentative_homepage_without_concrete_date_or_venue(self):
        from main import _passes_quality_gate

        ev = HackathonEvent(
            title="Hack The Boot: Italy's Signature Hackathon",
            url="https://hacktheboot.it/#hero-heading",
            source="web_search",
            description=(
                "Event Details: Spring 2026. Where: TBD, Italy. "
                "Very Soon. Pre-register now to be the first to know."
            ),
            date_str="",
            location="TBD, Italy",
        )

        ok, reason = _passes_quality_gate(ev)
        assert ok is False
        assert "data" in reason or "senza data" in reason

    def test_rejects_tum_makeathon_in_munich(self):
        from main import _passes_quality_gate

        ev = HackathonEvent(
            title="The TUM.ai Makeathon",
            url="https://makeathon.tum-ai.com",
            source="web_search",
            description="The Makeathon is in-person on TUM's campus in Munich during April.",
            date_str="2026-04-17",
            location="TUM Main Campus, Munich, Germany",
        )

        ok, reason = _passes_quality_gate(ev)
        assert ok is False
        assert "Milano" in reason or "non a Milano" in reason

    def test_cleanup_existing_events_removes_expired_and_known_duplicates(self):
        from main import _cleanup_existing_event_dicts

        expired = HackathonEvent(
            title="AI Voice Agent Hackathon powered by ElevenLabs - Milan",
            url="https://lu.ma/rgtc75im",
            source="luma",
            date_str="2026-03-07T08:30:00.000Z",
            location="Milano",
            is_hackathon=True,
        ).to_dict()
        duplicate = HackathonEvent(
            title="BCG Platinion Hackathon 2026 - Milano | Eightfold",
            url="https://experiencedtalent.bcg.com/events/candidate/registration?plannedEventId=aQnm026Vg",
            source="web_search",
            date_str="",
            location="Milano",
            is_hackathon=True,
        ).to_dict()
        valid = HackathonEvent(
            title="BCG Platinion Hackathon - Fighting World Hunger | October 16-17, 2026",
            url="https://www.bcgplatinion.com/hackathon",
            source="web_search",
            date_str="2026-10-16",
            location="Milano",
            is_hackathon=True,
        ).to_dict()

        out = _cleanup_existing_event_dicts([expired, duplicate, valid], ref_date=date(2026, 6, 30))

        assert [item["title"] for item in out] == [valid["title"]]
