"""
Test suite per filtri: keyword_filter e llm_filter.
"""

import json
from unittest.mock import patch, MagicMock

import pytest

import filters.keyword_filter as keyword_filter_module
from models import HackathonEvent
from filters.keyword_filter import keyword_filter, keyword_filter_batch
from filters.llm_filter import (
    _call_llm,
    _parse_llm_response,
    classify_batch,
    llm_filter,
    LLMResult,
)


# ─── Helper ──────────────────────────────────────────────────────────────────

def _make_event(title: str, description: str = "") -> HackathonEvent:
    return HackathonEvent(
        title=title, url=f"https://x.com/{hash(title)}", source="test",
        description=description,
    )


# =============================================================================
# Keyword Filter
# =============================================================================

class TestKeywordFilterPositive:
    """Keyword positive → l'evento PASSA al LLM (return True)."""

    @pytest.mark.parametrize("title", [
        "PoliHack 2026 — 24h coding marathon",
        "Best Hackathon in Milan",
        "Code Jam 2026",
        "Coding Challenge for students",
        "Buildathon at UniCredit",
        "HackFest Milano",
        "Appathon — build your app in 48h",
        "Makeathon Arduino — build hardware in 24h",
        "Global Game Jam Milano 2026",
        "Ideathon — pitch your idea",
        "Datathon open data Milano",
        "Startup Weekend Milano 2026",
        "Codefest Spring Edition",
        "Innovation Challenge PoliMi",
        "Tech Challenge Reply 2026",
        "Coding Contest universitario",
    ])
    def test_positive_keywords_pass(self, title):
        assert keyword_filter(_make_event(title)) is True


class TestKeywordFilterNegative:
    """Keyword negative → l'evento viene SCARTATO (return False)."""

    @pytest.mark.parametrize("title", [
        "Life Hacking Workshop",
        "Growth Hacking Meetup Milano",
        "IKEA Hack Day — furniture DIY",
        "Biohacking Conference 2026",
        "Growth Hacking Tips for Startups",
    ])
    def test_negative_keywords_rejected(self, title):
        assert keyword_filter(_make_event(title)) is False


class TestKeywordFilterAmbiguous:
    """Nessuna keyword → l'evento viene SCARTATO (restrittivo per free tier)."""

    @pytest.mark.parametrize("title", [
        "Conferenza sull'innovazione digitale",
        "Tech Event Milano 2026",
        "Random Event",
    ])
    def test_no_keyword_rejected(self, title):
        assert keyword_filter(_make_event(title)) is False

    def test_coding_sprint_still_passes(self):
        """'coding marathon' è una keyword positiva e deve passare."""
        assert keyword_filter(_make_event("48h coding marathon — build something amazing")) is True

    def test_announcement_teaser_with_future_date_and_milan_passes(self):
        title = "Il 9-10 maggio 2026 a Milano si svolgeranno due giornate dedicate allo spazio"
        assert keyword_filter(_make_event(title, "Fonte: telespazio.com")) is True

    def test_announcement_teaser_with_past_date_is_rejected(self):
        title = "Il 9-10 maggio 2024 a Milano si svolgeranno incontri tech"
        assert keyword_filter(_make_event(title, "Fonte: telespazio.com")) is False


class TestPastEventFilter:
    """Eventi con anno passato vengono scartati dal pre-filtro."""

    @pytest.mark.parametrize("title", [
        "Hackathon Milano 2024",
        "PoliHack 2023 — recap",
        "Global Game Jam 2025 SAE Milano",
        "Community Hackathon 2020 — risultati",
    ])
    def test_past_year_rejected(self, title):
        assert keyword_filter(_make_event(title)) is False

    @pytest.mark.parametrize("title", [
        "Hackathon Milano 2026",
        "Hackathon PoliMi 2027 — registrati ora",
        "Game Jam Milano 2026",
    ])
    def test_current_or_future_year_passes(self, title):
        assert keyword_filter(_make_event(title)) is True

    def test_mixed_years_passes_if_current_present(self):
        """'Hackathon 2025 → 2026 edition' contiene 2026 → passa."""
        assert keyword_filter(_make_event("Hackathon Milano 2025 → edizione 2026")) is True

    def test_no_year_passes_to_llm(self):
        """Senza anno, il filtro si affida alle keyword (poi al LLM)."""
        assert keyword_filter(_make_event("Hackathon Milano — prossima edizione")) is True


class TestKeywordFilterBatch:
    def test_batch_returns_correct_counts(self):
        events = [
            _make_event("Hackathon Milano"),          # positive → passa
            _make_event("Growth Hacking Workshop"),    # negative → scartato
            _make_event("Random Event"),               # no match → scartato
        ]
        passed, discarded = keyword_filter_batch(events)
        assert len(passed) == 1
        assert discarded == 2

    def test_empty_batch(self):
        passed, discarded = keyword_filter_batch([])
        assert passed == []
        assert discarded == 0


class TestKeywordFilterManualBlacklist:
    def test_manual_blacklist_rejects_event(self):
        event = _make_event(
            "Python Coding Challenge",
            "Challenge studentesca con premi",
        )

        with patch.object(keyword_filter_module, "_BLACKLIST", ["python coding challenge"]):
            assert keyword_filter(event) is False

    def test_online_itch_jam_url_rejected_before_llm(self):
        event = HackathonEvent(
            title="GameDev.tv Game Jam 2026",
            url="https://itch.io/jam/gamedevtv-jam-2026",
            source="web_search",
            description="A game jam hosted online with web build submissions.",
        )

        assert keyword_filter(event) is False


# =============================================================================
# LLM Filter — Parsing
# =============================================================================

class TestLLMParsing:
    def test_parse_array(self):
        content = json.dumps([
            {"index": 0, "is_hackathon": True, "confidence": 0.95, "reason": "yes"},
            {"index": 1, "is_hackathon": False, "confidence": 0.90, "reason": "no"},
        ])
        results = _parse_llm_response(content, 2)
        assert len(results) == 2
        assert results[0].is_hackathon is True
        assert results[0].confidence == 0.95
        assert results[1].is_hackathon is False

    def test_parse_wrapped_in_results(self):
        content = json.dumps({
            "results": [
                {"index": 0, "is_hackathon": True, "confidence": 0.80, "reason": "r"},
            ]
        })
        results = _parse_llm_response(content, 1)
        assert len(results) == 1
        assert results[0].is_hackathon is True

    def test_parse_pads_missing_results(self):
        """Se il LLM ritorna meno risultati del previsto, pad con default."""
        content = json.dumps([
            {"index": 0, "is_hackathon": True, "confidence": 0.9, "reason": "ok"},
        ])
        results = _parse_llm_response(content, 3)
        assert len(results) == 3
        assert results[0].confidence == 0.9
        # Padded results — default scarta per sicurezza
        assert results[1].is_hackathon is False
        assert results[1].confidence == 0.0
        assert results[2].is_hackathon is False
        assert results[2].confidence == 0.0

    def test_parse_truncates_extra_results(self):
        content = json.dumps([
            {"index": i, "is_hackathon": True, "confidence": 0.9, "reason": "r"}
            for i in range(5)
        ])
        results = _parse_llm_response(content, 2)
        assert len(results) == 2

    def test_parse_invalid_json_returns_default(self):
        results = _parse_llm_response("not valid json at all", 2)
        assert len(results) == 2
        assert all(r.is_hackathon is False for r in results)  # Default: scarta per sicurezza
        assert all(r.confidence == 0.0 for r in results)

    def test_parse_non_list_response(self):
        content = json.dumps({"some": "other structure"})
        results = _parse_llm_response(content, 1)
        assert len(results) == 1
        assert results[0].is_hackathon is False
        assert results[0].confidence == 0.0  # Default: scarta

    def test_parse_truncated_json_extracts_partial(self):
        """JSON troncato a metà: deve estrarre gli oggetti completi."""
        # Simula JSON troncato — il terzo oggetto è incompleto
        content = """[
            {"index": 0, "is_hackathon": true, "confidence": 0.99, "reason": "Hackathon vero"},
            {"index": 1, "is_hackathon": false, "confidence": 0.95, "reason": "Non è hackathon"},
            {"index": 2, "is_hackat"""
        results = _parse_llm_response(content, 3)
        assert len(results) == 3
        # I primi due devono essere estratti correttamente
        assert results[0].is_hackathon is True
        assert results[0].confidence == 0.99
        assert results[1].is_hackathon is False
        assert results[1].confidence == 0.95
        # Il terzo è mancante — default scarta per sicurezza
        assert results[2].is_hackathon is False
        assert results[2].confidence == 0.0


# =============================================================================
# LLM Filter — Graceful degradation
# =============================================================================

class TestLLMGracefulDegradation:
    @patch("filters.llm_filter.config")
    def test_no_api_key_returns_pass_with_low_confidence(self, mock_config):
        """Senza GROQ_API_KEY, tutti vengono scartati."""
        mock_config.GROQ_API_KEY = ""
        events = [_make_event("Hackathon Test")]
        results = classify_batch(events)
        assert len(results) == 1
        assert results[0].is_hackathon is False
        assert results[0].confidence == 0.0

    @patch("filters.llm_filter.config")
    def test_no_api_key_llm_filter_rejects_all(self, mock_config):
        """Senza API key: confidence 0.5 < threshold 0.7 → tutti scartati."""
        mock_config.GROQ_API_KEY = ""
        mock_config.LLM_CONFIDENCE_THRESHOLD = 0.7
        mock_config.LLM_BATCH_SIZE = 10
        events = [_make_event("Hackathon Test")]
        confirmed, discarded = llm_filter(events)
        assert len(confirmed) == 0
        assert discarded == 1


# =============================================================================
# LLM Filter — Con mock Groq
# =============================================================================

class TestLLMWithMockAPI:
    @patch("filters.llm_filter.config")
    @patch("filters.llm_filter._get_groq_client")
    def test_classify_batch_calls_groq(self, mock_get_client, mock_config):
        """Verifica che classify_batch chiama Groq correttamente."""
        mock_config.GROQ_API_KEY = "test-key"
        mock_config.LLM_MODEL = "llama-3.3-70b-versatile"
        mock_config.LLM_MAX_DESCRIPTION_LENGTH = 500
        mock_config.LLM_BATCH_SIZE = 10
        mock_config.LLM_RETRY_MAX = 3
        mock_config.LLM_RETRY_DELAY = 1

        # Mock client con response (OpenAI-compatible format)
        mock_client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = json.dumps([
            {"index": 0, "is_hackathon": True, "confidence": 0.95, "reason": "hackathon confirmed"}
        ])
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        events = [_make_event("PoliHack 2026")]
        results = classify_batch(events)

        assert len(results) == 1
        assert results[0].is_hackathon is True
        assert results[0].confidence == 0.95
        mock_client.chat.completions.create.assert_called_once()

    @patch("filters.llm_filter.config")
    @patch("filters.llm_filter._get_groq_client")
    def test_api_error_returns_default(self, mock_get_client, mock_config):
        """Se l'API va in errore, tutti vengono scartati per sicurezza."""
        mock_config.GROQ_API_KEY = "test-key"
        mock_config.LLM_MODEL = "llama-3.3-70b-versatile"
        mock_config.LLM_MAX_DESCRIPTION_LENGTH = 500
        mock_config.LLM_BATCH_SIZE = 10
        mock_config.LLM_RETRY_MAX = 3
        mock_config.LLM_RETRY_DELAY = 1

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("Server error")
        mock_get_client.return_value = mock_client

        events = [_make_event("Test")]
        results = classify_batch(events)

        assert len(results) == 1
        assert results[0].is_hackathon is False
        assert results[0].confidence == 0.0

    def test_parse_markdown_wrapped_json(self):
        """LLM a volte wrappa JSON in ```json ... ``` — deve essere gestito."""
        content = '```json\n[{"index": 0, "is_hackathon": true, "confidence": 0.9, "reason": "yes"}]\n```'
        results = _parse_llm_response(content, 1)
        assert len(results) == 1
        assert results[0].is_hackathon is True
        assert results[0].confidence == 0.9

    @patch("filters.llm_filter.config")
    @patch("filters.llm_filter._get_groq_client")
    def test_call_llm_uses_fallback_model(self, mock_get_client, mock_config):
        mock_config.LLM_MODEL = "primary-model"
        mock_config.LLM_MODEL_FALLBACKS = ["fallback-model"]
        mock_config.LLM_RETRY_MAX = 1
        mock_config.LLM_RETRY_DELAY = 0

        mock_client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = '{"results": []}'
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.side_effect = [
            Exception("model not found"),
            mock_response,
        ]
        mock_get_client.return_value = mock_client

        content = _call_llm("sys", "user")

        assert content == '{"results": []}'
        assert mock_client.chat.completions.create.call_count == 2
        first_model = mock_client.chat.completions.create.call_args_list[0].kwargs["model"]
        second_model = mock_client.chat.completions.create.call_args_list[1].kwargs["model"]
        assert first_model == "primary-model"
        assert second_model == "fallback-model"
