import json
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch

from models import HackathonEvent
from scripts import review_candidate as admin


def _event_dict(title: str, url: str = "https://example.com/event") -> dict:
    return HackathonEvent(
        title=title,
        url=url,
        source="test",
        description="Admin workflow test event",
        date_str="2026-06-10",
        location="Milano",
        is_hackathon=True,
        confidence=0.8,
    ).to_dict()


def _write_events(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"last_check": "2026-05-07T10:00:00+02:00", "events": events}),
        encoding="utf-8",
    )


def _write_queue(path: Path, candidates: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"updated_at": "2026-05-07T10:00:00+02:00", "count": len(candidates), "candidates": candidates}),
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@contextmanager
def _patched_admin_paths(tmp_path: Path):
    with ExitStack() as stack:
        stack.enter_context(patch.object(admin.config, "EVENTS_FILE", tmp_path / "events.json"))
        stack.enter_context(patch.object(admin.config, "REVIEW_QUEUE_FILE", tmp_path / "review_queue.json"))
        stack.enter_context(patch.object(admin.config, "REVIEW_DECISIONS_FILE", tmp_path / "review_decisions.json"))
        stack.enter_context(patch.object(admin.config, "BLACKLIST_FILE", tmp_path / "blacklist.txt"))
        stack.enter_context(patch.object(admin, "_rebuild_site"))
        yield


def test_move_published_event_to_review_queue(tmp_path: Path):
    event = _event_dict("Published Hackathon")

    with _patched_admin_paths(tmp_path):
        _write_events(admin.config.EVENTS_FILE, [event])
        _write_queue(admin.config.REVIEW_QUEUE_FILE, [])
        admin.config.REVIEW_DECISIONS_FILE.write_text(
            json.dumps({"decisions": {event["id"]: {"decision": "approved"}}}),
            encoding="utf-8",
        )

        admin.move_event_to_review("Published", note="Check venue")

        events_payload = _read_json(admin.config.EVENTS_FILE)
        queue_payload = _read_json(admin.config.REVIEW_QUEUE_FILE)
        decisions_payload = _read_json(admin.config.REVIEW_DECISIONS_FILE)

    assert events_payload["events"] == []
    assert queue_payload["count"] == 1
    assert queue_payload["candidates"][0]["id"] == event["id"]
    assert queue_payload["candidates"][0]["review_status"] == "needs_review"
    assert queue_payload["candidates"][0]["review_reason"] == "Check venue"
    assert event["id"] not in decisions_payload["decisions"]


def test_approve_candidate_publishes_event_and_records_decision(tmp_path: Path):
    candidate = _event_dict("Candidate Hackathon", "https://example.com/candidate")
    candidate["review_status"] = "needs_review"

    with _patched_admin_paths(tmp_path):
        _write_events(admin.config.EVENTS_FILE, [])
        _write_queue(admin.config.REVIEW_QUEUE_FILE, [candidate])

        admin.approve_candidate(candidate["id"][:12])

        events_payload = _read_json(admin.config.EVENTS_FILE)
        queue_payload = _read_json(admin.config.REVIEW_QUEUE_FILE)
        decisions_payload = _read_json(admin.config.REVIEW_DECISIONS_FILE)

    assert len(events_payload["events"]) == 1
    assert events_payload["events"][0]["title"] == "Candidate Hackathon"
    assert events_payload["events"][0]["review_status"] == "manual_approved"
    assert queue_payload["count"] == 0
    assert decisions_payload["decisions"][candidate["id"]]["decision"] == "approved"


def test_reject_candidate_removes_from_queue_and_suppresses_future(tmp_path: Path):
    candidate = _event_dict("Rejected Hackathon", "https://example.com/rejected")

    with _patched_admin_paths(tmp_path):
        _write_events(admin.config.EVENTS_FILE, [])
        _write_queue(admin.config.REVIEW_QUEUE_FILE, [candidate])

        admin.reject_candidate(candidate["id"][:12])

        queue_payload = _read_json(admin.config.REVIEW_QUEUE_FILE)
        decisions_payload = _read_json(admin.config.REVIEW_DECISIONS_FILE)

    assert queue_payload["count"] == 0
    assert decisions_payload["decisions"][candidate["id"]]["decision"] == "rejected"


def test_dismiss_candidate_removes_from_queue_without_decision(tmp_path: Path):
    candidate = _event_dict("Dismissed Hackathon", "https://example.com/dismissed")

    with _patched_admin_paths(tmp_path):
        _write_events(admin.config.EVENTS_FILE, [])
        _write_queue(admin.config.REVIEW_QUEUE_FILE, [candidate])

        admin.dismiss_candidate(candidate["id"][:12])

        queue_payload = _read_json(admin.config.REVIEW_QUEUE_FILE)
        decisions_exists = admin.config.REVIEW_DECISIONS_FILE.exists()

    assert queue_payload["count"] == 0
    assert decisions_exists is False


def test_remove_event_can_blacklist_title(tmp_path: Path):
    event = _event_dict("Bad Published Hackathon", "https://example.com/bad")

    with _patched_admin_paths(tmp_path):
        _write_events(admin.config.EVENTS_FILE, [event])

        admin.remove_event("Bad Published", add_blacklist=True)

        events_payload = _read_json(admin.config.EVENTS_FILE)
        blacklist = admin.config.BLACKLIST_FILE.read_text(encoding="utf-8")

    assert events_payload["events"] == []
    assert "bad published hackathon" in blacklist
