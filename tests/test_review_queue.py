import json
from pathlib import Path
from unittest.mock import patch

from models import HackathonEvent
from utils.html_export import generate_html
from utils.review_queue import (
    build_review_queue,
    load_review_decisions,
    load_review_queue,
    save_review_decisions,
    save_review_queue,
)


def _event(
    title: str,
    url: str,
    *,
    is_hackathon: bool,
    confidence: float,
) -> HackathonEvent:
    return HackathonEvent(
        title=title,
        url=url,
        source="test",
        is_hackathon=is_hackathon,
        confidence=confidence,
        review_reason="test reason",
    )


def test_queue_includes_low_confidence_hackathon_candidates():
    candidate = _event(
        "Maybe Hackathon",
        "https://example.com/maybe",
        is_hackathon=True,
        confidence=0.62,
    )

    queue = build_review_queue([candidate], confirmed=[])

    assert len(queue) == 1
    assert queue[0]["id"] == candidate.id
    assert queue[0]["review_status"] == "needs_review"


def test_queue_includes_uncertain_rejections_but_skips_confident_noise():
    uncertain = _event(
        "Possible challenge",
        "https://example.com/possible",
        is_hackathon=False,
        confidence=0.58,
    )
    confident_noise = _event(
        "Regular meetup",
        "https://example.com/meetup",
        is_hackathon=False,
        confidence=0.92,
    )

    queue = build_review_queue([uncertain, confident_noise], confirmed=[])

    assert [item["id"] for item in queue] == [uncertain.id]


def test_queue_skips_confirmed_errors_and_manual_decisions():
    confirmed = _event(
        "Confirmed Hackathon",
        "https://example.com/confirmed",
        is_hackathon=True,
        confidence=0.95,
    )
    llm_error = _event(
        "API Error Candidate",
        "https://example.com/error",
        is_hackathon=False,
        confidence=0.0,
    )
    rejected = _event(
        "Rejected Candidate",
        "https://example.com/rejected",
        is_hackathon=True,
        confidence=0.6,
    )

    queue = build_review_queue(
        [confirmed, llm_error, rejected],
        confirmed=[confirmed],
        decisions={rejected.id: {"decision": "rejected"}},
    )

    assert queue == []


def test_review_queue_roundtrip(tmp_path: Path):
    queue_path = tmp_path / "review_queue.json"
    decisions_path = tmp_path / "review_decisions.json"
    candidate = _event(
        "Roundtrip Candidate",
        "https://example.com/roundtrip",
        is_hackathon=True,
        confidence=0.6,
    )
    queue = build_review_queue([candidate], confirmed=[])

    save_review_queue(queue, queue_path)
    save_review_decisions({candidate.id: {"decision": "approved"}}, decisions_path)

    assert load_review_queue(queue_path)[0]["id"] == candidate.id
    assert load_review_decisions(decisions_path)[candidate.id]["decision"] == "approved"


def test_static_site_writes_review_page(tmp_path: Path):
    events_path = tmp_path / "events.json"
    review_path = tmp_path / "review_queue.json"
    report_path = tmp_path / "last_report.json"
    index_path = tmp_path / "index.html"
    review_output_path = tmp_path / "review.html"
    candidate = _event(
        "Manual Check Hackathon",
        "https://example.com/manual-check",
        is_hackathon=True,
        confidence=0.61,
    )
    queue = build_review_queue([candidate], confirmed=[])

    events_path.write_text(
        json.dumps(
            {
                "last_check": "2026-05-03T10:00:00",
                "events": [
                    {
                        "title": "Confirmed Hackathon",
                        "url": "https://example.com/confirmed",
                        "source": "test",
                        "is_hackathon": True,
                        "confidence": 0.95,
                        "date_str": "2026-06-15",
                        "location": "Milano",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    report_path.write_text(
        json.dumps({"status": "completed", "failed_collectors": []}),
        encoding="utf-8",
    )
    save_review_queue(queue, review_path)

    with (
        patch("utils.html_export.config.DATA_DIR", tmp_path),
        patch("utils.html_export.config.REVIEW_QUEUE_FILE", review_path),
    ):
        generate_html(
            events_path=events_path,
            output_path=index_path,
            review_output_path=review_output_path,
        )

    assert "Candidati in review" in index_path.read_text(encoding="utf-8")
    index_html = index_path.read_text(encoding="utf-8")
    review_html = review_output_path.read_text(encoding="utf-8")
    assert "Valuta OK" in index_html
    assert "/issues/new" in index_html
    assert "Manual Check Hackathon" in review_html
    assert "Segnala dubbio" in review_html


def test_static_site_ignores_stale_local_report(tmp_path: Path):
    events_path = tmp_path / "events.json"
    review_path = tmp_path / "review_queue.json"
    report_path = tmp_path / "last_report.json"
    index_path = tmp_path / "index.html"
    review_output_path = tmp_path / "review.html"

    events_path.write_text(
        json.dumps(
            {
                "last_check": "2026-05-11T15:48:41+02:00",
                "events": [
                    {
                        "title": "Confirmed Hackathon",
                        "url": "https://example.com/confirmed",
                        "source": "test",
                        "is_hackathon": True,
                        "confidence": 0.95,
                        "date_str": "2099-06-15",
                        "location": "Milano",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    report_path.write_text(
        json.dumps(
            {
                "date": "2026-05-03 13:41",
                "status": "llm_failed_preserved",
                "failed_collectors": [],
            }
        ),
        encoding="utf-8",
    )
    save_review_queue([], review_path)

    with (
        patch("utils.html_export.config.DATA_DIR", tmp_path),
        patch("utils.html_export.config.REVIEW_QUEUE_FILE", review_path),
    ):
        generate_html(
            events_path=events_path,
            output_path=index_path,
            review_output_path=review_output_path,
        )

    index_html = index_path.read_text(encoding="utf-8")
    assert "LLM non attivo" not in index_html
    assert "<strong>OK</strong>" in index_html
