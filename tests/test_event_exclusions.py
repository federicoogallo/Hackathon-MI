"""Previously reported events stay excluded across their known URL aliases."""

from datetime import date

import pytest

from filters.event_exclusions import event_exclusion_reason
from filters.keyword_filter import keyword_filter
from main import _cleanup_existing_event_dicts, _passes_quality_gate
from models import HackathonEvent


EXCLUDED_URLS = [
    ("https://www.gsom.polimi.it/knowledge/harvard-hsil-hackathon-2026", "passato"),
    ("https://gsom.polimi.it/en/knowledge/harvard-hsil-hackathon-2026/?utm_source=mail#details", "passato"),
    ("https://luma.com/5fxlxfl5", "passato"),
    ("https://www.lu.ma/5fxlxfl5/?ref=calendar#details", "passato"),
    ("https://lablab.ai/ai-hackathons/milan-ai-week-hackathon/?utm_source=search", "passato"),
    ("https://www.lablab.ai/ai-hackathons/milan-ai-week-hackathon/project/demo#details", "passato"),
    ("https://www.eventbrite.com/e/ai-agent-olympics-milan-ai-week-hackathon-tickets-1987936520647?aff=search", "passato"),
    ("https://eventbrite.it/e/biglietti-ai-agent-olympics-1987936520647/#tickets", "passato"),
    ("https://gdg.community.dev/events/details/google-gdg-on-campus-polytechnic-university-of-milan-presents-gdg-ai-hack-2026/", "passato"),
    ("https://www.gdg.community.dev/events/details/google-gdg-on-campus-polytechnic-university-of-milan-presents-gdg-ai-hack-2026/?utm_source=mail#details", "passato"),
    ("https://bcg.eightfold.ai/events/candidate/landing?plannedEventId=aQnm026Vg", "duplicato"),
    ("https://bcg.eightfold.ai/events/candidate/registration/?utm_source=mail&plannedEventId=aQnm026Vg#details", "duplicato"),
    ("https://experiencedtalent.bcg.com/events/candidate/registration?plannedEventId=aQnm026Vg", "duplicato"),
    ("https://www.experiencedtalent.bcg.com/events/candidate/landing/?ref=email&plannedEventId=aQnm026Vg#details", "duplicato"),
    ("https://polimi.it/il-politecnico/eventi/dettaglio-evento/innovation-challenge-2026-soluzioni-per-evitare-la-disillusione-dellai", "convegno"),
    ("https://www.polimi.it/il-politecnico/eventi/dettaglio-evento/innovation-challenge-2026-soluzioni-per-evitare-la-disillusione-dellai/?utm_source=mail#details", "convegno"),
]


def _candidate(url: str, date_str: str = "") -> HackathonEvent:
    return HackathonEvent(
        title="Hackathon Milano 2026",
        url=url,
        source="web_search",
        description="Hackathon in presenza a Milano con sviluppo di prototipi.",
        location="Milano",
        date_str=date_str,
    )


@pytest.mark.parametrize("url,reason_fragment", EXCLUDED_URLS)
@pytest.mark.parametrize("date_str", ["", "2026-12-01"])
def test_verified_exclusions_override_missing_or_incorrect_future_dates(url, reason_fragment, date_str):
    event = _candidate(url, date_str)

    assert keyword_filter(event) is False
    quality_ok, reason = _passes_quality_gate(event)
    assert quality_ok is False
    assert reason_fragment in reason


@pytest.mark.parametrize("url", [
    "https://www.bcgplatinion.com/hackathon",
    "https://bcg.eightfold.ai/events/candidate/landing?plannedEventId=lj5b3dmvQ",
    "https://experiencedtalent.bcg.com/events/candidate/registration?plannedEventId=aQnm026Vg-new",
    "https://www.gsom.polimi.it/knowledge/harvard-hsil-hackathon-2027",
    "https://gdg.community.dev/events/details/google-gdg-on-campus-polytechnic-university-of-milan-presents-gdg-ai-hack-2027/",
    "https://www.polimi.it/il-politecnico/eventi/dettaglio-evento/innovation-challenge-2027-soluzioni-per-evitare-la-disillusione-dellai",
    "https://luma.com/another-event",
    "https://lablab.ai/ai-hackathons/milan-ai-week-hackathon-2027",
    "https://www.eventbrite.it/e/biglietti-ai-agent-olympics-1987936520648",
])
def test_other_editions_and_canonical_bcg_remain_eligible(url):
    event = _candidate(url, "2026-10-16")

    assert event_exclusion_reason(url) is None
    assert keyword_filter(event) is True
    assert _passes_quality_gate(event) == (True, "ok")


def test_exclusions_match_the_host_and_event_id_not_an_embedded_url():
    assert event_exclusion_reason(
        "https://example.com/?url=https://luma.com/5fxlxfl5"
    ) is None
    assert event_exclusion_reason(
        "https://gsom.polimi.it.example.com/knowledge/harvard-hsil-hackathon-2026"
    ) is None
    assert event_exclusion_reason(
        "https://bcg.eightfold.ai/events/candidate/landing?other=plannedEventId=aQnm026Vg"
    ) is None


def test_cleanup_removes_reported_aliases_and_keeps_official_bcg():
    excluded = [_candidate(url).to_dict() for url, _ in EXCLUDED_URLS]
    canonical = HackathonEvent(
        title="BCG Platinion Hackathon 2026",
        url="https://www.bcgplatinion.com/hackathon",
        source="web_search",
        description="Hackathon BCG Platinion in presenza a Milano il 16–17 ottobre 2026.",
        date_str="2026-10-16",
        location="Milano",
    ).to_dict()

    cleaned = _cleanup_existing_event_dicts(
        [*excluded, canonical], ref_date=date(2026, 9, 19)
    )

    assert cleaned == [canonical]
