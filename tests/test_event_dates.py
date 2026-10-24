"""Regression cases for stale announcements and source-date ambiguity."""

from datetime import date

import pytest

from models import HackathonEvent
from utils.event_dates import event_temporal_status


TODAY = date(2026, 10, 22)


def candidate(**fields):
    return HackathonEvent(
        title=fields.pop("title", "Accessibility Hackathon Milano"),
        url="https://example.com/event", source="web_search", **fields,
    )


@pytest.mark.parametrize("text,status", [
    ("Save the date: Saturday, September 26th, 2026, Milan!", "past"),
    ("Il nostro hackathon si terrà il 26 settembre 2026 a Milano.", "past"),
    ("Save the date: September 26th, Milan.", "uncertain"),
    ("Hackathon il 26 settembre a Milano.", "uncertain"),
    ("Hackathon il 20 novembre 2026 a Milano.", "future"),
    ("Hackathon il 22 ottobre 2026 a Milano.", "future"),
    ("Hackathon on 2026-09-26 in Milan.", "past"),
    ("Hackathon il 26/09/2026 a Milano.", "past"),
    ("Hackathon il 31 novembre 2026 a Milano.", "uncertain"),
    ("Posted on September 16, 2026. Save the date: September 26th, Milan.", "uncertain"),
    ("Hackathon: applications close September 16, 2026.", "unknown"),
    ("Application deadline for the hackathon: September 16, 2026.", "unknown"),
    ("Hackathon registration opens November 20, 2026.", "unknown"),
    ("Hackathon: iscrizioni entro il 16 settembre 2026.", "unknown"),
    ("Published October 21, 2026. An accessibility challenge in Milano.", "unknown"),
    ("Hackathon on September 26, 2026. Hackathon on November 20, 2026.", "uncertain"),
    ("Hackathon on September 26, 2026. Published October 21, 2026.", "past"),
])
def test_event_dates_in_source_announcements(text, status):
    event = candidate(description=text)
    before = event.to_dict()
    assert event_temporal_status(event, TODAY) == status
    assert event.to_dict() == before


@pytest.mark.parametrize("date_str", ["21–23 ottobre 2026", "October 21-23, 2026"])
def test_source_date_range_is_kept_through_last_day(date_str):
    event = candidate(date_str=date_str)
    assert event_temporal_status(event, TODAY) == "future"
    assert event_temporal_status(event, date(2026, 10, 23)) == "future"
    assert event_temporal_status(event, date(2026, 10, 24)) == "past"


def test_structured_future_event_date_takes_precedence_over_history():
    event = candidate(date_str="2026-11-20T09:00:00+01:00", date_source="event",
                      description="Our last hackathon was held on September 26, 2026.")
    assert event_temporal_status(event, TODAY) == "future"


@pytest.mark.parametrize("date_source", ["publication", "deadline", "unknown"])
def test_non_event_date_cannot_override_stale_announcement(date_source):
    event = candidate(date_str="2026-11-20", date_source=date_source,
                      description="Save the date: September 26, 2026.")
    assert event_temporal_status(event, TODAY) == "past"


def test_discovery_publication_and_llm_reason_never_supply_the_year():
    event = candidate(description="Save the date: September 26th, Milan!",
                      discovered_at="2026-10-21", published_at="2026-09-16",
                      review_reason="Future hackathon on 2027-09-26", confidence=0.99)
    assert event_temporal_status(event, TODAY) == "uncertain"


def test_new_discovery_does_not_make_past_structured_date_future():
    event = candidate(date_str="2026-09-26", discovered_at="2026-10-21")
    assert event_temporal_status(event, TODAY) == "past"


def test_date_in_event_title_is_recognized_without_snippet():
    event = candidate(title="AI Hackathon in Milan 24 October 2026 | Albert School")
    assert event_temporal_status(event, TODAY) == "future"


def test_deadline_in_title_is_not_an_event_date():
    event = candidate(title="Hackathon application deadline: September 26, 2026")
    assert event_temporal_status(event, TODAY) == "unknown"
