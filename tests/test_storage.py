"""
Test suite per storage/json_store.py — EventStore con dedup a due livelli.
"""

import json
from pathlib import Path

import pytest

from models import HackathonEvent
from storage.json_store import EventStore


@pytest.fixture
def tmp_events_file(tmp_path: Path) -> Path:
    """Percorso temporaneo per il file eventi."""
    return tmp_path / "events.json"


@pytest.fixture
def store(tmp_events_file: Path) -> EventStore:
    """EventStore vuoto con percorso temporaneo."""
    return EventStore(path=tmp_events_file)


@pytest.fixture
def sample_event() -> HackathonEvent:
    return HackathonEvent(
        title="PoliHack 2026",
        url="https://example.com/polihack2026",
        source="test",
        description="Hackathon al Politecnico di Milano, 24h coding marathon.",
        date_str="2026-03-15",
        organizer="PoliMi",
    )


# ─── Caricamento / Salvataggio ───────────────────────────────────────────────

class TestPersistence:
    def test_save_and_reload(self, tmp_events_file, sample_event):
        """Salva un evento, poi ricrea lo store → l'evento è presente."""
        store = EventStore(path=tmp_events_file)
        store.add_event(sample_event)
        store.save_with_timestamp("2026-01-01T00:00:00")

        # Ricarica da file
        store2 = EventStore(path=tmp_events_file)
        assert store2.count == 1
        assert store2.has_event(sample_event.id)

    def test_handles_missing_file(self, tmp_path):
        """Se il file non esiste, lo store parte vuoto senza crash."""
        store = EventStore(path=tmp_path / "nonexistent.json")
        assert store.count == 0

    def test_handles_corrupted_file(self, tmp_events_file):
        """Se il file è corrotto, lo store parte vuoto."""
        tmp_events_file.write_text("{ corrupted json // }")
        store = EventStore(path=tmp_events_file)
        assert store.count == 0

    def test_handles_empty_events_list(self, tmp_events_file):
        """Se la lista è vuota, lo store parte vuoto."""
        tmp_events_file.write_text(json.dumps({"events": []}))
        store = EventStore(path=tmp_events_file)
        assert store.count == 0

    def test_save_creates_parent_dirs(self, tmp_path, sample_event):
        """save() crea le directory padre se non esistono."""
        nested = tmp_path / "a" / "b" / "events.json"
        store = EventStore(path=nested)
        store.add_event(sample_event)
        store.save()
        assert nested.exists()


# ─── Dedup Livello 1: URL esatto ────────────────────────────────────────────

class TestDedupLevel1:
    def test_exact_url_is_duplicate(self, store, sample_event):
        store.add_event(sample_event)
        assert store.is_duplicate(sample_event) is True

    def test_url_with_trailing_slash_is_duplicate(self, store):
        """URL con e senza trailing slash → stesso ID → duplicato."""
        e1 = HackathonEvent(title="A", url="https://x.com/e", source="s1")
        e2 = HackathonEvent(title="A", url="https://x.com/e/", source="s2")
        store.add_event(e1)
        assert store.is_duplicate(e2) is True

    def test_url_with_utm_is_duplicate(self, store):
        """URL con UTM params normalizzato → stesso ID → duplicato."""
        e1 = HackathonEvent(title="A", url="https://x.com/e", source="s1")
        e2 = HackathonEvent(title="A", url="https://x.com/e?utm_source=tw", source="s2")
        store.add_event(e1)
        assert store.is_duplicate(e2) is True

    def test_different_url_is_not_duplicate(self, store, sample_event):
        store.add_event(sample_event)
        different = HackathonEvent(title="Other", url="https://other.com/x", source="test")
        assert store.is_duplicate(different) is False


# ─── Dedup Livello 2: Fuzzy titolo ──────────────────────────────────────────

class TestDedupLevel2:
    def test_similar_title_different_url_is_duplicate(self, store):
        """Titoli quasi identici con URL diversi → fuzzy match → duplicato."""
        e1 = HackathonEvent(
            title="PoliHack Milano 2026 Hackathon",
            url="https://source1.com/polihack2026",
            source="s1",
        )
        e2 = HackathonEvent(
            title="PoliHack Milano 2026 Hackathon Edition",
            url="https://source2.com/polihack",
            source="s2",
        )
        store.add_event(e1)
        assert store.is_duplicate(e2) is True

    def test_very_different_title_is_not_duplicate(self, store):
        """Titoli completamente diversi → non duplicato."""
        e1 = HackathonEvent(title="PoliHack 2026", url="https://a.com/1", source="s1")
        e2 = HackathonEvent(title="Climate Tech Challenge", url="https://b.com/2", source="s2")
        store.add_event(e1)
        assert store.is_duplicate(e2) is False

    def test_fuzzy_match_adds_alternate_url(self, store):
        """Quando fuzzy match, l'URL alternativo viene aggiunto allo storico."""
        e1 = HackathonEvent(
            title="PoliHack Milano 2026 Hackathon",
            url="https://source1.com/ph",
            source="s1",
        )
        e2 = HackathonEvent(
            title="PoliHack Milano 2026 Hackathon Event",
            url="https://source2.com/ph",
            source="s2",
        )
        store.add_event(e1)
        store.is_duplicate(e2)

        # Verifichiamo che l'URL alternativo sia stato salvato
        stored = store._events[e1.id]
        assert "alternate_urls" in stored
        assert "https://source2.com/ph" in stored["alternate_urls"]


# ─── Count / Add ────────────────────────────────────────────────────────────

class TestAddEvent:
    def test_add_increments_count(self, store):
        assert store.count == 0
        e = HackathonEvent(title="A", url="https://x.com/a", source="s")
        store.add_event(e)
        assert store.count == 1

    def test_add_multiple_events(self, store):
        for i in range(5):
            store.add_event(HackathonEvent(title=f"E{i}", url=f"https://x.com/{i}", source="s"))
        assert store.count == 5
