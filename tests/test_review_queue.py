from pathlib import Path

from models import HackathonEvent
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
