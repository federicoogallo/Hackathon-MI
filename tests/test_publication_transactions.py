"""Publication failures preserve the previous catalog and review generation."""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

import config
from models import HackathonEvent
from storage.files import (
    CorruptDataFile, publication_transaction, read_json, recover_publication, write_json,
)
from utils import scan_metrics


def test_second_save_failure_restores_both_files(tmp_path):
    archive, queue = tmp_path / "events.json", tmp_path / "review_queue.json"
    journal = tmp_path / ".publication-transaction.json"
    archive.write_text('{"events": ["old"]}\n')
    queue.write_text('{"candidates": []}\n')
    originals = [p.read_bytes() for p in (archive, queue)]
    with pytest.raises(OSError, match="second save"):
        with publication_transaction([archive, queue], journal):
            write_json(archive, {"events": ["new"]})
            raise OSError("second save")
    assert [p.read_bytes() for p in (archive, queue)] == originals
    assert not journal.exists()


def test_first_publication_rollback_removes_created_files(tmp_path):
    archive, queue = tmp_path / "events.json", tmp_path / "review_queue.json"
    journal = tmp_path / ".publication-transaction.json"
    with pytest.raises(RuntimeError):
        with publication_transaction([archive, queue], journal):
            write_json(archive, {"events": []})
            raise RuntimeError("interrupted")
    assert not archive.exists() and not queue.exists() and not journal.exists()


def test_process_exit_is_recovered_before_the_next_publication(tmp_path):
    archive, queue = tmp_path / "events.json", tmp_path / "review_queue.json"
    journal = tmp_path / ".publication-transaction.json"
    archive.write_text('{"events": ["old"]}')
    queue.write_text('{"candidates": ["old"]}')
    program = """
import os, sys
from pathlib import Path
from storage.files import publication_transaction, write_json
folder = Path(sys.argv[1])
paths = [folder / 'events.json', folder / 'review_queue.json']
with publication_transaction(paths, folder / '.publication-transaction.json'):
    write_json(paths[0], {'events': ['new']})
    os._exit(23)
"""
    result = subprocess.run([sys.executable, "-B", "-c", program, str(tmp_path)],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True)
    assert result.returncode == 23
    assert read_json(archive)["events"] == ["new"]
    assert journal.stat().st_mode & 0o777 == 0o600
    assert recover_publication([archive, queue], journal)
    assert read_json(archive)["events"] == ["old"]
    assert read_json(queue)["candidates"] == ["old"]
    assert not recover_publication([archive, queue], journal)


def test_recovery_validates_every_entry_before_restoring(tmp_path):
    archive, queue = tmp_path / "events.json", tmp_path / "review_queue.json"
    journal = tmp_path / ".publication-transaction.json"
    archive.write_text('{"events": []}')
    with publication_transaction([archive, queue], journal):
        saved = read_json(journal)
    saved["files"][1]["path"] = str(tmp_path / "unrelated.json")
    write_json(journal, saved)
    with pytest.raises(CorruptDataFile):
        recover_publication([archive, queue], journal)
    assert archive.read_text() == '{"events": []}' and journal.exists()
    assert not (tmp_path / "unrelated.json").exists()


def test_failed_rollback_keeps_journal_for_retry(tmp_path):
    archive, queue = tmp_path / "events.json", tmp_path / "review_queue.json"
    journal = tmp_path / ".publication-transaction.json"
    write_json(archive, {"events": ["old"]})
    with publication_transaction([archive, queue], journal):
        saved = journal.read_bytes()
    journal.write_bytes(saved)
    write_json(archive, {"events": ["new"]})
    with patch("storage.files.os.replace", side_effect=OSError("disk unavailable")):
        with pytest.raises(OSError):
            recover_publication([archive, queue], journal)
    assert journal.exists()
    assert recover_publication([archive, queue], journal)
    assert read_json(archive)["events"] == ["old"]


def test_pipeline_rolls_back_catalog_when_queue_save_fails(tmp_path, monkeypatch):
    import main

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main, "_now", lambda: datetime(2026, 11, 1, tzinfo=timezone.utc))
    old = HackathonEvent(title="Existing data challenge", url="https://example.org/old", source="s",
                         date_str="2026-12-20", date_source="event", location="Milano",
                         is_hackathon=True, confidence=0.95, review_status="ai_verified")
    new = HackathonEvent(title="New climate hackathon", url="https://example.org/new", source="s",
                         date_str="2026-12-21", date_source="event", location="Milano",
                         is_hackathon=True, confidence=0.95, review_status="ai_verified",
                         classification_status="confirmed")
    write_json(config.EVENTS_FILE, {"last_check": "2026-10-31", "events": [old.to_dict()]})
    write_json(config.REVIEW_QUEUE_FILE, {"count": 0, "candidates": []})
    originals = [p.read_bytes() for p in (config.EVENTS_FILE, config.REVIEW_QUEUE_FILE)]
    monkeypatch.setattr(main, "get_collectors", lambda: ["s"])
    monkeypatch.setattr(main, "run_collectors", lambda _: ([new], ["s"], [], [
        {"name": "s", "ok": True, "status": "healthy", "event_count": 1, "issues": []},
    ]))
    monkeypatch.setattr(main, "keyword_filter_batch", lambda events: (events, 0))
    monkeypatch.setattr(main, "llm_filter", lambda events: (events, 0))
    monkeypatch.setattr(main, "llm_dedup", lambda events: events)
    with patch("main.save_review_queue", side_effect=OSError("queue write failed")):
        with pytest.raises(OSError, match="queue write failed"):
            main.run_pipeline()
    assert [p.read_bytes() for p in (config.EVENTS_FILE, config.REVIEW_QUEUE_FILE)] == originals
    assert not (tmp_path / ".publication-transaction.json").exists()
    [record] = scan_metrics.load_history()
    assert record["status"] == "crashed"
    assert json.loads((tmp_path / "last_report.json").read_text())["status"] == "crashed"
