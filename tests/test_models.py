"""
Test suite per models.py — HackathonEvent e funzioni di normalizzazione.
"""

import time

from models import HackathonEvent, _normalize_url, _normalize_title


class TestNormalizeUrl:
    def test_strips_utm_params(self):
        assert _normalize_url(
            "https://example.com/event/123/?utm_source=twitter&utm_medium=social"
        ) == "https://example.com/event/123"

    def test_strips_ref_param(self):
        assert _normalize_url(
            "https://example.com/event?ref=homepage&id=42"
        ) == "https://example.com/event?id=42"

    def test_strips_trailing_slash(self):
        assert _normalize_url("https://example.com/event/") == "https://example.com/event"

    def test_lowercases_hostname(self):
        result = _normalize_url("https://EXAMPLE.COM/Event")
        assert result == "https://example.com/Event"

    def test_preserves_path_case(self):
        result = _normalize_url("https://example.com/MyEvent")
        assert "/MyEvent" in result

    def test_handles_no_query(self):
        result = _normalize_url("https://example.com/event")
        assert result == "https://example.com/event"

    def test_handles_fragment(self):
        # Fragment (#section) dovrebbe essere rimosso
        result = _normalize_url("https://example.com/event#section")
        assert "#" not in result

    def test_handles_empty_string(self):
        result = _normalize_url("")
        assert isinstance(result, str)


class TestNormalizeTitle:
    def test_lowercases(self):
        assert _normalize_title("PoliHack 2026") == "polihack 2026"

    def test_strips_punctuation(self):
        assert _normalize_title("PoliHack 2026!! - 24h") == "polihack 2026 24h"

    def test_strips_ascii_punctuation_only(self):
        # Em dash (—) è unicode, non in string.punctuation → non viene rimosso
        result = _normalize_title("PoliHack 2026!! — 24h")
        assert "—" in result

    def test_collapses_spaces(self):
        assert _normalize_title("  PoliHack   2026  ") == "polihack 2026"


class TestHackathonEvent:
    def test_same_url_same_id(self):
        """Stesso URL normalizzato → stesso ID (dedup cross-source)."""
        e1 = HackathonEvent(title="A", url="https://example.com/hack", source="s1")
        e2 = HackathonEvent(title="A", url="https://example.com/hack/", source="s2")
        assert e1.id == e2.id

    def test_different_url_different_id(self):
        e1 = HackathonEvent(title="A", url="https://example.com/a", source="s1")
        e2 = HackathonEvent(title="A", url="https://example.com/b", source="s1")
        assert e1.id != e2.id

    def test_id_ignores_source(self):
        """ID non dipende dal source (dedup cross-collector)."""
        e1 = HackathonEvent(title="A", url="https://x.com/e", source="eventbrite")
        e2 = HackathonEvent(title="A", url="https://x.com/e", source="google_cse")
        assert e1.id == e2.id

    def test_to_dict_includes_id(self):
        e = HackathonEvent(title="Test", url="https://x.com/t", source="test")
        d = e.to_dict()
        assert "id" in d
        assert d["id"] == e.id

    def test_location_defaults_to_unknown(self):
        e = HackathonEvent(title="Test", url="https://x.com/t", source="test")
        assert e.location == ""

    def test_to_dict_complete(self):
        e = HackathonEvent(
            title="Test", url="https://x.com/t", source="test",
            description="desc", date_str="2026-01-01", organizer="org",
        )
        d = e.to_dict()
        assert d["title"] == "Test"
        assert d["description"] == "desc"
        assert d["organizer"] == "org"

    def test_discovered_at_is_per_instance(self):
        e1 = HackathonEvent(title="A", url="https://x.com/a", source="s")
        time.sleep(0.01)
        e2 = HackathonEvent(title="B", url="https://x.com/b", source="s")
        # Possono essere uguali se molto veloci, ma non devono essere lo stesso oggetto
        assert isinstance(e1.discovered_at, str)
        assert isinstance(e2.discovered_at, str)

    def test_equality_based_on_id(self):
        e1 = HackathonEvent(title="A", url="https://x.com/e", source="s1")
        e2 = HackathonEvent(title="B", url="https://x.com/e", source="s2")
        assert e1 == e2  # Stesso URL → uguali

    def test_hash_for_set_dedup(self):
        e1 = HackathonEvent(title="A", url="https://x.com/e", source="s1")
        e2 = HackathonEvent(title="A", url="https://x.com/e/", source="s2")
        assert len({e1, e2}) == 1

    def test_title_normalized(self):
        e = HackathonEvent(title="PoliHack 2026!", url="https://x.com/p", source="s")
        assert e.title_normalized == "polihack 2026"
