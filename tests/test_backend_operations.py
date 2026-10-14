"""Operational regressions with no external requests, API calls or notifications."""

import json
from datetime import date
from unittest.mock import MagicMock, patch
import pytest

from bs4 import BeautifulSoup

import config
from collectors.eventbrite import EventbriteCollector
from collectors.startup_italia import StartupItaliaCollector
from main import _manually_rejected, run_collectors, run_pipeline
from models import HackathonEvent
from storage.json_store import EventStore
from utils.candidate_audit import CandidateAudit
from utils.collector_health import record_issue, track_collector
from utils.http import safe_get, safe_get_json
from utils.review_queue import build_review_queue, save_review_queue


def event(name="Aurora", **kwargs):
    return HackathonEvent(title=f"{name} Hackathon Milano", url=f"https://example.org/{name}",
                          source="test", **kwargs)


class HttpCollector:
    def __init__(self, name, urls):
        self.name, self.urls = name, urls

    def collect(self):
        records = []
        for url in self.urls:
            if safe_get(url) is not None:
                records.append(event(self.name))
        return records


def test_parallel_http_failures_are_not_healthy_and_partial_records_survive():
    def response(url, **kwargs):
        return MagicMock(status_code=404 if "broken" in url else 200)
    session = MagicMock()
    session.get.side_effect = response
    with patch("utils.http.get_session", return_value=session):
        records, ok, failed, runs = run_collectors([
            HttpCollector("working", ["https://example.org/ok"]),
            HttpCollector("broken", ["https://example.org/broken"]),
            HttpCollector("partial", ["https://example.org/ok", "https://example.org/broken"]),
        ])
    assert {record.source for record in records} == {"test"}
    assert len(records) == 2
    assert ok == ["working"]
    assert len(failed) == 2
    assert {item["name"]: item["status"] for item in runs} == {
        "working": "healthy", "broken": "failed", "partial": "degraded",
    }


def test_missing_credentials_are_disabled_not_empty_or_failed(monkeypatch):
    monkeypatch.setattr(config, "EVENTBRITE_API_KEY", "")
    records, ok, failed, runs = run_collectors([EventbriteCollector()])
    assert records == ok == failed == []
    assert runs[0]["status"] == "disabled"
    assert not runs[0]["ok"]


def test_blocked_response_and_malformed_json_have_diagnostics_without_secrets():
    session = MagicMock()
    session.get.return_value = MagicMock(status_code=403)
    with patch("utils.http.get_session", return_value=session), track_collector() as health:
        assert safe_get("https://user:password@example.org/events?token=secret") is None
    assert health.outcome(0) == "blocked"
    assert health.issues[0]["endpoint"] == "https://example.org/events"
    assert "secret" not in json.dumps(health.issues)
    session.get.return_value = MagicMock(status_code=200)
    session.get.return_value.json.side_effect = ValueError("bad JSON")
    with patch("utils.http.get_session", return_value=session), track_collector() as health:
        assert safe_get_json("https://example.org/events") is None
    assert health.outcome(0) == "degraded"
    assert health.issues[0]["kind"] == "parse_error"


def test_editorial_date_does_not_make_future_announcement_past():
    html = '''<article><a href="/hackathon"><h2>Hackathon Milano 2026</h2></a>
        <time datetime="2026-10-01">1 ottobre</time>
        <p class="excerpt">Il 20 novembre 2026 si terrà un hackathon a Milano.</p></article>'''
    candidate = StartupItaliaCollector()._parse_card(BeautifulSoup(html, "lxml").article,
                                                    "https://example.org/", set())
    assert candidate.published_at == "2026-10-01"
    assert candidate.date_str == ""
    assert candidate.is_upcoming(date(2026, 10, 11))


def test_review_retains_unseen_pending_and_information_on_weaker_rediscovery():
    rich = event(date_str="2026-12-02", classification_status="insufficient_evidence", confidence=.99)
    pending = build_review_queue([rich], [], ref_date=date(2026, 7, 1))
    pending[0]["queued_at"] = "2026-07-01T12:00:00+00:00"
    assert build_review_queue([], [], previous=pending, ref_date=date(2026, 10, 11)) == pending
    weak = event(classification_status="insufficient_evidence", confidence=.99)
    queue = build_review_queue([weak], [], previous=pending, ref_date=date(2026, 10, 11))
    assert len(queue) == 1
    assert queue[0]["date_str"] == "2026-12-02"
    assert queue[0]["queued_at"] == pending[0]["queued_at"]


def test_review_removes_resolved_past_and_expired_undated_candidates():
    future = event("future", date_str="2099-12-02", confidence=.6, is_hackathon=True)
    past = event("past", date_str="2026-09-26", confidence=.6, is_hackathon=True)
    unknown = event("unknown", confidence=.6, is_hackathon=True)
    pending = build_review_queue([future, past, unknown], [], ref_date=date(2026, 9, 1))
    for item in pending:
        item["queued_at"] = "2026-07-01T12:00:00Z"
    assert build_review_queue([], [], {future.id: {"decision": "rejected"}},
                              previous=pending, ref_date=date(2026, 10, 11)) == []


def test_manual_rejection_applies_to_alternate_source_urls():
    candidate = event()
    rejected = event("rejected")
    candidate.alternate_urls = [rejected.url]
    assert _manually_rejected(candidate, {rejected.id: {"decision": "rejected"}})


def test_audit_is_bounded_private_and_contains_stage_evidence(tmp_path):
    candidate = event(description="Event source excerpt")
    audit = CandidateAudit()
    audit.stage("keyword", [candidate], [], {candidate.id: "not a build competition"})
    for _ in range(32):
        audit.save(str(tmp_path))
    files = list(tmp_path.glob("candidates-*.json"))
    assert len(files) == 30
    data = json.loads(files[0].read_text())
    assert data["stages"][0]["records"][0]["outcome"] == "excluded"
    assert files[0].stat().st_mode & 0o777 == 0o600
    assert audit.summary() == [{"stage": "keyword", "input": 1, "output": 0}]


@pytest.mark.parametrize("dry_run", [True, False])
def test_total_collection_failure_preserves_archive_and_last_check(tmp_path, monkeypatch, dry_run):
    archive = tmp_path / "events.json"
    archive.write_text(json.dumps({"last_check": "2026-10-09T12:00:00Z", "events": []}))
    original = archive.read_bytes()
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    with patch("main.EventStore", return_value=EventStore(archive)), \
         patch("main.get_collectors", return_value=["broken"]), \
         patch("main.run_collectors", return_value=([], [], ["broken: HTTP 404"],
               [{"name": "broken", "ok": False, "status": "failed"}])), \
         patch("main.llm_filter") as classify, patch("main.notify_run_summary") as notify:
        run_pipeline(dry_run=dry_run)
    assert archive.read_bytes() == original
    classify.assert_not_called()
    if dry_run:
        notify.assert_not_called()
    else:
        notify.assert_called_once()
        assert notify.call_args.kwargs["scan_status"] == "collection_failed_preserved"
        assert notify.call_args.kwargs["collector_runs"][0]["name"] == "broken"
    assert json.loads((tmp_path / "last_report.json").read_text())["status"] == "collection_failed_preserved"


def test_partial_classification_error_retains_review_and_marks_degraded(tmp_path, monkeypatch):
    good = event("Aurora", date_str="2099-12-02", location="Via Confalonieri 4, Milano")
    bad = event("Nebula", date_str="2099-12-03", location="Milano")
    def classify(events):
        for candidate in events:
            if candidate.id == good.id:
                candidate.is_hackathon = True
                candidate.confidence = .99
                candidate.classification_status = "confirmed"
            else:
                candidate.classification_status = "error"
                candidate.review_reason = "API error"
        return [candidate for candidate in events if candidate.is_hackathon], 1
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "REVIEW_QUEUE_FILE", tmp_path / "queue.json")
    monkeypatch.setattr(config, "REVIEW_DECISIONS_FILE", tmp_path / "decisions.json")
    with patch("main.EventStore", return_value=EventStore(tmp_path / "events.json")), \
         patch("main.get_collectors", return_value=["test"]), \
         patch("main.run_collectors", return_value=([good, bad], ["test"], [],
               [{"name": "test", "ok": True, "status": "healthy"}])), \
         patch("main.llm_filter", side_effect=classify), patch("main.llm_dedup", side_effect=lambda events: events), \
         patch("main.generate_html"), patch("main.generate_readme_table"), \
         patch("main.notify_run_summary") as notify:
        run_pipeline(dry_run=True)
    report = json.loads((tmp_path / "last_report.json").read_text())
    assert report["status"] == "degraded"
    assert not report["classification_completed"]
    assert report["classification_errors"] == 1
    assert report["new_events"] == 1
    assert json.loads((tmp_path / "queue.json").read_text())["candidates"][0]["id"] == bad.id
    notify.assert_not_called()
