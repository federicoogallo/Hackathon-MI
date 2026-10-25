from datetime import date
from pathlib import Path

import pytest

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
    location: str = "Politecnico di Milano",
) -> HackathonEvent:
    return HackathonEvent(
        title=title,
        url=url,
        source="test",
        location=location,
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


def test_uncertain_candidates_without_any_milan_reference_are_not_queued():
    # Search collectors add a generic "Milano" location to every result.
    foreign = HackathonEvent(title="Global AI Hackathon 2026", url="https://unstop.com/hackathons/global-ai",
                             source="web_search", location="Milano", confidence=0.9,
                             classification_status="insufficient_evidence")
    milanese = HackathonEvent(title="Hackathon PoliHub", url="https://polihub.it/news-it/hackathon",
                              source="web_search", confidence=0.9, classification_status="insufficient_evidence")
    stale = {**foreign.to_dict(), "id": "stale", "queued_at": "2026-10-20T00:00:00+00:00"}
    never_judged = HackathonEvent(title="Global AI Hackathon", url="https://example.org/error",
                                  source="web_search", classification_status="error")

    queue = build_review_queue([foreign, milanese, never_judged], confirmed=[], previous=[stale])

    assert {item["id"] for item in queue} == {milanese.id, never_judged.id}


def test_milan_signal_reads_url_slugs_and_specific_locations():
    from utils.review_queue import has_milan_signal

    assert has_milan_signal({"title": "European Builders League", "url": "https://luma.com/milan-ebl"})
    assert has_milan_signal({"title": "Hackathon", "url": "https://x.org", "location": "Via Imbonati 18, Milano"})
    # A bare city is evidence when read from the event, not when echoed by a search query.
    assert has_milan_signal({"title": "Hackathon", "url": "https://x.org", "location": "Milano", "source": "eventbrite_web"})
    assert not has_milan_signal({"title": "Hackathon", "url": "https://x.org", "location": "Milano", "source": "web_search"})
    assert not has_milan_signal({"title": "Hackathon Milanino Lab", "url": "https://x.org"})


@pytest.mark.parametrize("source", ["eventbrite_web", "luma", "meetup"])
@pytest.mark.parametrize("city", ["Milano", "Rho", "Segrate", "Cinisello Balsamo"])
def test_structured_city_keeps_a_local_event_reviewable(source, city):
    event = HackathonEvent(title="AI Builders Night", url="https://www.eventbrite.it/e/ai-builders-123",
                           source=source, location=city, date_str="2026-11-20",
                           date_source="event_jsonld", confidence=0.9, classification_status="insufficient_evidence")
    assert len(build_review_queue([event], confirmed=[], ref_date=date(2026, 10, 25))) == 1


def test_queued_range_stays_until_its_last_day():
    event = HackathonEvent(title="Sfida PoliMi", url="https://www.polimi.it/il-politecnico/eventi/dettaglio-evento/sfida",
                           source="universities", organizer="Politecnico di Milano",
                           date_str="2026-11-04 — 2026-11-11", date_source="event_card",
                           confidence=0.9, classification_status="insufficient_evidence")
    queue = build_review_queue([event], confirmed=[], ref_date=date(2026, 10, 25))
    assert len(build_review_queue([], confirmed=[], previous=queue, ref_date=date(2026, 11, 5))) == 1
    assert build_review_queue([], confirmed=[], previous=queue, ref_date=date(2026, 11, 12)) == []


def test_shorter_rediscovery_keeps_the_queued_milan_evidence():
    first = HackathonEvent(title="Agents Hackathon", url="https://luma.com/agents-x", source="web_search",
                           description="Hackathon in presenza a Milano, dettagli in arrivo",
                           confidence=0.9, classification_status="insufficient_evidence")
    queue = build_review_queue([first], confirmed=[], ref_date=date(2026, 10, 25))
    again = HackathonEvent(title="Agents Hackathon", url="https://luma.com/agents-x", source="web_search",
                           confidence=0.9, classification_status="insufficient_evidence")

    queue = build_review_queue([again], confirmed=[], previous=queue, ref_date=date(2026, 10, 26))

    assert len(queue) == 1
    assert "Milano" in queue[0]["description"]


def test_new_date_and_shorter_text_preserve_location_evidence_across_scans(tmp_path):
    first = HackathonEvent(title="Agents Hackathon", url="https://luma.com/agents-x", source="web_search",
                           description="Hackathon in presenza a Milano, dettagli in arrivo",
                           confidence=0.9, classification_status="insufficient_evidence")
    queue = build_review_queue([first], confirmed=[], ref_date=date(2026, 10, 25))
    again = HackathonEvent(title=first.title, url=first.url, source="web_search",
                           description="Iscrizioni aperte.", date_str="2026-11-20", date_source="event",
                           confidence=0.9, classification_status="insufficient_evidence")
    queue = build_review_queue([again], confirmed=[], previous=queue, ref_date=date(2026, 10, 26))
    path = tmp_path / "queue.json"
    save_review_queue(queue, path)
    queue = build_review_queue([], confirmed=[], previous=load_review_queue(path), ref_date=date(2026, 10, 27))

    assert len(queue) == 1
    assert queue[0]["date_str"] == "2026-11-20"
    assert queue[0]["description"] == "Iscrizioni aperte."
    assert queue[0]["review_location_evidence"]["description"] == first.description
    # Stored evidence must neither overrule a rejection nor leak into a new edition.
    again.classification_status = "rejected"
    again.confidence = 0.99
    assert build_review_queue([again], confirmed=[], previous=queue, ref_date=date(2026, 10, 27)) == []
    again.classification_status = "insufficient_evidence"
    again.date_str = "2027-11-20"
    assert build_review_queue([again], confirmed=[], previous=queue, ref_date=date(2026, 10, 27)) == []
