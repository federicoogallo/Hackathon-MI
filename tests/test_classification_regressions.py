"""Keep uncertain source evidence reviewable without converting it into facts."""

import json
from datetime import datetime
from unittest.mock import patch

import pytest

import filters.keyword_filter as keywords
from filters.llm_filter import (
    _build_user_prompt,
    _get_system_prompt,
    _parse_llm_response,
    llm_dedup,
    llm_filter,
)
from models import HackathonEvent


def candidate(**overrides):
    return HackathonEvent(**{
        "title": "Hackathon Milano 2026",
        "url": "https://example.org/hackathon",
        "source": "test",
        "date_str": "2026-11-20",
        "location": "Università Bocconi, Milano",
        **overrides,
    })


def judgment(index=0, **overrides):
    return {
        "index": index,
        "is_hackathon": True,
        "confidence": 0.95,
        "reason": "Supported by source evidence",
        **overrides,
    }


@pytest.mark.parametrize("partial", [False, True])
@pytest.mark.parametrize("wrapped", [False, True])
def test_classification_uses_indices_for_complete_and_truncated_results(partial, wrapped):
    entries = [judgment(2, is_hackathon=False), judgment(0)]
    content = json.dumps({"results": entries} if wrapped else entries)
    if partial:
        content = content[:-(2 if wrapped else 1)] + ', {"index": 1, "is_hackathon":'

    results = _parse_llm_response(content, 3)

    assert results[0].is_hackathon is True
    assert results[0].status == "confirmed"
    assert results[1].status == "error"
    assert results[1].is_hackathon is False
    assert results[2].status == "rejected"


@pytest.mark.parametrize("partial", [False, True])
def test_duplicate_index_invalidates_only_ambiguous_slot(partial):
    entries = [judgment(0), judgment(0, is_hackathon=False), judgment(1)]
    content = json.dumps({"results": entries})
    if partial:
        content = content[:-2] + ', {"index":'
    results = _parse_llm_response(content, 2)

    assert results[0].status == "error"
    assert results[0].confidence == 0
    assert results[1].is_hackathon is True


@pytest.mark.parametrize("bad_index", [True, False, "0", 0.0, -1, 9, None, [], {}])
def test_invalid_indices_never_fall_back_to_array_position(bad_index):
    results = _parse_llm_response(json.dumps([judgment(bad_index), judgment(1)]), 2)
    assert results[0].status == "error"
    assert results[1].is_hackathon is True


@pytest.mark.parametrize("override", [
    {"is_hackathon": "false"}, {"is_hackathon": "true"},
    {"is_hackathon": 1}, {"is_hackathon": None},
    {"confidence": "0.95"}, {"confidence": True},
    {"confidence": -0.1}, {"confidence": 1.1}, {"confidence": 10 ** 500},
    {"confidence": float("nan")}, {"confidence": float("inf")},
    {"reason": None}, {"reason": {"text": "yes"}},
    {"status": {}}, {"status": []}, {"status": None},
    {"status": "unknown"}, {"status": "rejected"},
    {"status": "insufficient_evidence"},
    {"status": "error", "is_hackathon": False, "confidence": 0.8},
    {"status": "confirmed", "is_hackathon": False},
])
def test_malformed_classifications_fail_closed_and_preserve_other_slots(override):
    results = _parse_llm_response(json.dumps([judgment(0, **override), judgment(1)]), 2)
    assert results[0].status == "error"
    assert results[0].confidence == 0
    assert results[0].is_hackathon is False
    assert results[1].is_hackathon is True


@pytest.mark.parametrize("missing", ["index", "is_hackathon", "confidence", "reason"])
def test_required_fields_cannot_default_to_approval(missing):
    item = judgment()
    del item[missing]
    result = _parse_llm_response(json.dumps([item]), 1)[0]
    assert result.status == "error"
    assert result.is_hackathon is False


def test_nested_fact_objects_cannot_become_classifications_during_partial_recovery():
    content = json.dumps({"results": [{"index": 0, "source_fact": judgment(1)}]})[:-2] + ', {"index":'
    results = _parse_llm_response(content, 2)
    assert all(result.status == "error" for result in results)


def test_insufficient_evidence_is_not_published_and_preserves_source_facts():
    event = candidate(date_str="", description="An announced hackathon with details to follow.")
    facts = (event.title, event.url, event.description, event.date_str, event.location)
    parsed = _parse_llm_response(json.dumps([judgment(
        status="insufficient_evidence", is_hackathon=False,
        reason="Event date unavailable", event_date="Invented date",
    )]), 1)
    with patch("filters.llm_filter.classify_batch", return_value=parsed):
        confirmed, discarded = llm_filter([event])
    assert confirmed == []
    assert discarded == 1
    assert event.classification_status == "insufficient_evidence"
    assert event.review_status == "needs_review"
    assert (event.title, event.url, event.description, event.date_str, event.location) == facts


@pytest.mark.parametrize("source", ["", "event_api", "event_jsonld", "event_card", "manual"])
def test_prompt_includes_source_event_date_separately_from_publication(source):
    event = candidate(date_source=source, published_at="2026-10-01")
    prompt = _build_user_prompt([event])
    assert 'Data evento dalla fonte: "2026-11-20"' in prompt
    assert 'Pubblicazione articolo (non data evento): "2026-10-01"' in prompt


@pytest.mark.parametrize("source", ["publication", "unknown", "deadline"])
def test_prompt_does_not_present_uncertain_dates_as_event_dates(source):
    prompt = _build_user_prompt([candidate(date_source=source)])
    assert 'Data evento dalla fonte: "(non verificata)"' in prompt
    assert "2026-11-20" not in prompt


def test_prompt_requires_evidence_even_on_direct_event_pages():
    prompt = _get_system_prompt()
    assert "insufficient_evidence" in prompt
    assert "Pubblicazione articolo" in prompt
    assert "anche su una pagina diretta con form di registrazione, NON pubblicare" in prompt


class AuditClock(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 11, 12, 0, 0, tzinfo=tz)


@pytest.mark.parametrize("description", [
    "Premi per i vincitori della sfida di sviluppo.",
    "Un workshop gratuito precede la sfida di sviluppo di 24 ore.",
    "Workshop introduttivo e hackathon di 24 ore con premi per i vincitori.",
])
def test_incidental_prizes_and_workshops_reach_classifier_for_future_hackathons(description):
    with patch.object(keywords, "datetime", AuditClock):
        assert keywords.keyword_filter(candidate(description=description)) is True


def test_precise_future_date_in_announcement_can_contextualize_prizes():
    with patch.object(keywords, "datetime", AuditClock):
        assert keywords.keyword_filter(candidate(
            date_str="", description="Hackathon il 20 novembre 2026 a Milano. Premi per i vincitori.",
        )) is True


@pytest.mark.parametrize("overrides", [
    {"title": "Workshop gratuito Milano", "description": "Premi per i vincitori."},
    {"date_str": "", "description": "Hackathon 2026. Premi per i vincitori."},
    {"date_str": "2026-09-20", "description": "Premi per i vincitori."},
    {"description": "Recap del hackathon. Premi per i vincitori."},
    {"description": "Vincitori annunciati: si è svolto l'hackathon a Milano."},
    {"description": "Hackathon: premiati i vincitori."},
    {"description": "Career fair con hackathon e workshop gratuito."},
    {"url": "https://itch.io/jam/test", "description": "Premi per i vincitori."},
])
def test_contextual_keyword_exceptions_keep_hard_exclusions(overrides):
    with patch.object(keywords, "datetime", AuditClock):
        assert keywords.keyword_filter(candidate(**overrides)) is False


def test_contextual_keyword_exception_never_bypasses_manual_blacklist():
    with patch.object(keywords, "datetime", AuditClock), patch.object(keywords, "_BLACKLIST", ["hackathon milano"]):
        assert keywords.keyword_filter(candidate(description="Premi per i vincitori.")) is False


@pytest.mark.parametrize("source", ["publication", "unknown", "deadline"])
def test_keyword_year_filter_does_not_mistake_editorial_or_unknown_dates_for_event_dates(source):
    with patch.object(keywords, "datetime", AuditClock):
        assert keywords.keyword_filter(candidate(
            title="Hackathon Milano", date_str="2024-10-01", date_source=source,
        )) is True


def test_llm_cannot_merge_separate_editions():
    first = candidate(title="Bocconi AI Hackathon 2026", date_str="2026-11-20")
    second = candidate(title="Bocconi AI Hackathon 2027", url="https://example.org/next", date_str="2027-03-20")
    answer = json.dumps([{"group": [0, 1], "best_title": first.title, "best_url": first.url}])
    with patch("filters.llm_filter.config.GROQ_API_KEY", "fixture"), patch("filters.llm_filter._call_llm", return_value=answer):
        assert llm_dedup([first, second]) == [first, second]
    assert second.url not in first.alternate_urls


def test_llm_cannot_merge_same_date_events_using_shared_generic_words():
    first = candidate(title="GreenBuild", description="Teams design sustainability prototypes with mentors.")
    second = candidate(title="OpenFinance", url="https://example.org/finance", description="Teams design financial prototypes with mentors.")
    answer = json.dumps([{"group": [0, 1]}])
    with patch("filters.llm_filter.config.GROQ_API_KEY", "fixture"), patch("filters.llm_filter._call_llm", return_value=answer):
        assert llm_dedup([first, second]) == [first, second]


def test_llm_can_select_an_existing_source_record_for_proven_duplicates():
    first = candidate(title="Bocconi Anthropic AI Hackathon")
    second = candidate(title=first.title, url="https://example.org/official")
    answer = json.dumps([{"group": [0, 1], "best_url": second.url, "best_title": second.title}])
    with patch("filters.llm_filter.config.GROQ_API_KEY", "fixture"), patch("filters.llm_filter._call_llm", return_value=answer):
        assert llm_dedup([first, second]) == [second]
    assert first.url in second.alternate_urls
