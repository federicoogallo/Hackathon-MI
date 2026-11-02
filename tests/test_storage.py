"""
Test suite per storage/json_store.py — EventStore con dedup a due livelli.
"""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from models import HackathonEvent
from storage.files import CorruptDataFile, read_json, write_json
from storage.json_store import EventStore
from utils.review_queue import (
    load_review_decisions, load_review_queue, save_review_queue,
)


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

    @pytest.mark.parametrize("content", ["{ corrupted json // }", "", '{"events": [{"id": "a"', "[]",
                                         '{"events": {}}'])
    def test_an_unreadable_archive_stops_instead_of_starting_empty(self, tmp_events_file, content):
        """An empty store would overwrite every record at the next save."""
        tmp_events_file.write_text(content)
        with pytest.raises(CorruptDataFile) as stopped:
            EventStore(path=tmp_events_file)
        assert "events.json non leggibile" in str(stopped.value)
        assert tmp_events_file.read_text() == content

    def test_handles_empty_events_list(self, tmp_events_file):
        """Se la lista è vuota, lo store parte vuoto."""
        tmp_events_file.write_text(json.dumps({"events": []}))
        store = EventStore(path=tmp_events_file)
        assert store.count == 0

    @pytest.mark.parametrize("payload, reason", [
        ({"last_check": "2026-11-01"}, "manca la lista events"),
        ({"events": [None]}, "non è un oggetto"),
        ({"events": ["private-content"]}, "non è un oggetto"),
        ({"events": [{"title": "private-content"}]}, "id deve essere"),
        *[({"events": [{"id": value}]}, "id deve essere")
          for value in (None, "", "  ", 1, True, [], {})],
        ({"events": [{"id": "private-content"}, {"id": "private-content", "title": "new"}]},
         "id duplicato"),
        *[({"events": [{"id": "private-content", "alternate_urls": value}]}, "alternate_urls")
          for value in (None, "https://example.org", [{}], [1])],
    ])
    def test_invalid_records_cannot_disappear_while_loading(self, tmp_events_file, payload, reason):
        original = json.dumps(payload).encode("utf-8")
        tmp_events_file.write_bytes(original)

        with pytest.raises(CorruptDataFile) as stopped:
            EventStore(path=tmp_events_file)

        assert reason in stopped.value.reason
        assert "private-content" not in str(stopped.value)
        assert tmp_events_file.read_bytes() == original

    def test_valid_legacy_records_and_extra_fields_are_preserved(self, tmp_events_file):
        records = [{"id": "legacy-id", "extra": {"keep": True}},
                   {"id": "another-id", "alternate_urls": ["https://example.org/mirror"]}]
        tmp_events_file.write_text(json.dumps({"events": records}))

        assert EventStore(tmp_events_file).all_events() == records

    def test_save_creates_parent_dirs(self, tmp_path, sample_event):
        """save() crea le directory padre se non esistono."""
        nested = tmp_path / "a" / "b" / "events.json"
        store = EventStore(path=nested)
        store.add_event(sample_event)
        store.save()
        assert nested.exists()

    def test_touch_last_check_preserves_events_payload(self, tmp_events_file):
        """touch_last_check aggiorna solo il timestamp, senza riscrivere gli eventi in memoria."""
        payload = {
            "last_check": "2026-04-14T13:38:46",
            "events": [
                {
                    "id": "abc",
                    "title": "Evento validato",
                    "url": "https://example.com/e",
                    "alternate_urls": ["https://mirror.example.com/e"],
                }
            ],
            "extra": {"keep": True},
        }
        tmp_events_file.write_text(json.dumps(payload), encoding="utf-8")
        store = EventStore(path=tmp_events_file)

        store.touch_last_check("2026-05-03T13:45:18+02:00")

        updated = json.loads(tmp_events_file.read_text(encoding="utf-8"))
        assert updated["last_check"] == "2026-05-03T13:45:18+02:00"
        assert updated["events"] == payload["events"]
        assert updated["extra"] == payload["extra"]

    @pytest.mark.parametrize("payload", [{}, {"events": [{"id": "same"}, {"id": "same"}]}])
    def test_touch_rechecks_structure_before_replacing_a_changed_file(self, tmp_events_file, payload):
        store = EventStore(tmp_events_file)
        original = json.dumps(payload).encode("utf-8")
        tmp_events_file.write_bytes(original)

        with pytest.raises(CorruptDataFile):
            store.touch_last_check("2026-11-01T12:00:00+01:00")

        assert tmp_events_file.read_bytes() == original


class TestDataFiles:
    def test_write_replaces_the_file_in_one_rename(self, tmp_path):
        path = tmp_path / "events.json"
        path.write_text('{"events": []}')
        os.chmod(path, 0o640)
        write_json(path, {"events": [{"id": "a"}]})
        assert read_json(path) == {"events": [{"id": "a"}]}
        assert path.stat().st_mode & 0o777 == 0o640
        assert [item.name for item in tmp_path.iterdir()] == ["events.json"]

    def test_an_interrupted_write_keeps_the_previous_file(self, tmp_path):
        path = tmp_path / "events.json"
        path.write_text('{"events": [{"id": "old"}]}')
        with patch("storage.files.os.replace", side_effect=OSError("disk full")), pytest.raises(OSError):
            write_json(path, {"events": []})
        assert read_json(path) == {"events": [{"id": "old"}]}
        assert [item.name for item in tmp_path.iterdir()] == ["events.json"]

    def test_missing_file_is_none_and_wrong_shape_is_corrupt(self, tmp_path):
        assert read_json(tmp_path / "missing.json") is None
        (tmp_path / "list.json").write_text("[1]")
        assert read_json(tmp_path / "list.json", list) == [1]
        with pytest.raises(CorruptDataFile, match="atteso dict, trovato list"):
            read_json(tmp_path / "list.json")

    def test_review_files_are_strict_too(self, tmp_path):
        """A queue or a decision file read as empty would lose candidates or manual rejections."""
        queue, decisions = tmp_path / "review_queue.json", tmp_path / "review_decisions.json"
        assert load_review_queue(queue) == [] and load_review_decisions(decisions) == {}
        queue.write_text('{"candidates": [')
        decisions.write_text('{"decisions": []}')
        with pytest.raises(CorruptDataFile):
            load_review_queue(queue)
        with pytest.raises(CorruptDataFile, match="decisions non è un oggetto"):
            load_review_decisions(decisions)
        save_review_queue([{"id": "a"}], queue)
        assert load_review_queue(queue) == [{"id": "a"}]

    @pytest.mark.parametrize("payload, reason", [
        ({"updated_at": "2026-11-01"}, "manca la lista candidates"),
        ({"candidates": {}}, "candidates non è una lista"),
        ({"candidates": [None]}, "non è un oggetto"),
        ({"candidates": ["private-content"]}, "non è un oggetto"),
        ({"candidates": [{"title": "private-content"}]}, "id deve essere"),
        *[({"candidates": [{"id": value}]}, "id deve essere")
          for value in (None, "", "  ", 1, True, [], {})],
        ({"candidates": [{"id": "private-content"}, {"id": "private-content"}]}, "id duplicato"),
        *[({"candidates": [{"id": "private-content"}], "count": value}, "count deve essere")
          for value in (0, 2, "1", 1.0, True, None)],
    ])
    def test_queue_rejects_invalid_records_before_they_can_be_overwritten(self, tmp_path, payload, reason):
        path = tmp_path / "review_queue.json"
        original = json.dumps(payload).encode("utf-8")
        path.write_bytes(original)

        with pytest.raises(CorruptDataFile) as stopped:
            load_review_queue(path)

        assert reason in stopped.value.reason
        assert "private-content" not in str(stopped.value)
        assert path.read_bytes() == original

    @pytest.mark.parametrize("include_count", [False, True])
    def test_queue_keeps_legacy_records_and_extra_fields(self, tmp_path, include_count):
        path = tmp_path / "review_queue.json"
        candidates = [{"id": "legacy-id", "extra": {"keep": True}}]
        payload = {"candidates": candidates}
        if include_count:
            payload["count"] = len(candidates)
        path.write_text(json.dumps(payload))

        assert load_review_queue(path) == candidates

    @pytest.mark.parametrize("payload, reason", [
        ({"updated_at": "2026-11-01"}, "manca l'oggetto decisions"),
        ({"decisions": []}, "decisions non è un oggetto"),
        *[({"decisions": {key: {"decision": "rejected"}}}, "id deve essere")
          for key in ("", "  ")],
        *[({"decisions": {"private-content": value}}, "non è un oggetto")
          for value in (None, [], "rejected")],
        ({"decisions": {"private-content": {"reason": "private-content"}}}, "decision deve essere"),
        *[({"decisions": {"private-content": {"decision": value}}}, "decision deve essere")
          for value in (None, "", "private-content", True, [], {})],
    ])
    def test_malformed_decisions_cannot_be_silently_ignored(self, tmp_path, payload, reason):
        path = tmp_path / "review_decisions.json"
        original = json.dumps(payload).encode("utf-8")
        path.write_bytes(original)

        with pytest.raises(CorruptDataFile) as stopped:
            load_review_decisions(path)

        assert reason in stopped.value.reason
        assert "private-content" not in str(stopped.value)
        assert path.read_bytes() == original

    def test_both_decisions_and_their_optional_metadata_survive_loading(self, tmp_path):
        path = tmp_path / "review_decisions.json"
        decisions = {"legacy-approved": {"decision": "approved"},
                     "legacy-rejected": {"decision": "rejected", "reason": "keep", "extra": [1]}}
        path.write_text(json.dumps({"decisions": decisions}))

        assert load_review_decisions(path) == decisions


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
