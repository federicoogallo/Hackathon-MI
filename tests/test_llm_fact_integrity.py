"""The AI may classify and select source records, never supply event facts."""

import json
import logging
from unittest.mock import patch

import pytest

from filters.llm_filter import _parse_llm_response, llm_dedup, llm_filter
from models import HackathonEvent
from scripts.extract_dates import main as audit_dates
from scripts.slow_classify import slow_classify


def _event(title="Source title", date_str=""):
    return HackathonEvent(
        title=title,
        url="https://example.com/official",
        source="test",
        description="A source excerpt, without a precise date.",
        date_str=date_str,
    )


def _facts(event):
    return {field: getattr(event, field) for field in (
        "title", "url", "source", "description", "date_str", "location", "organizer",
    )}


@pytest.mark.parametrize("date_str", ["", "2026-11-20"])
@pytest.mark.parametrize("classify", [llm_filter, slow_classify])
def test_classifiers_ignore_llm_fact_completion(date_str, classify):
    event = _event(date_str=date_str)
    original = _facts(event)
    response = json.dumps({"results": [{
        "index": 0,
        "is_hackathon": True,
        "confidence": 0.99,
        "reason": "Relevant event",
        "event_date": "2026-12-01",
        "title": "Generated title",
        "description": "Generated description",
        "location": "Invented venue, Milan",
        "organizer": "Invented organizer",
    }]})
    results = _parse_llm_response(response, 1)

    with patch("filters.llm_filter.classify_batch", return_value=results), \
         patch("scripts.slow_classify._call_groq_no_retry", return_value=results):
        confirmed = classify([event]) if classify is llm_filter else classify([event], delay=0)

    assert (confirmed[0] if classify is llm_filter else confirmed) == [event]
    assert _facts(event) == original
    assert event.is_hackathon is True


def test_truncated_llm_response_does_not_reintroduce_date_completion():
    content = '[{"index": 0, "is_hackathon": true, "confidence": 0.99, "reason": "ok", "event_date": "2026-12-01"}, {"index":'
    results = _parse_llm_response(content, 2)

    assert results[0].is_hackathon is True
    assert vars(results[0]) == {"is_hackathon": True, "confidence": 0.99, "reason": "ok"}
    assert results[1].is_hackathon is False


@pytest.mark.parametrize("best_title", ["Invented title", "Other event", None, {"title": "Injected"}])
def test_dedup_rejects_titles_not_present_in_group(best_title):
    article = _event("News headline")
    article.url = "https://example.com/news"
    official = _event("Official hackathon title", "2026-11-20")
    other = _event("Other event")
    other.url = "https://example.com/other"
    original = _facts(official)
    response = json.dumps([{
        "group": [0, 1], "best_url": official.url, "best_title": best_title,
    }])

    with patch("filters.llm_filter.config.GROQ_API_KEY", "test-key"), \
         patch("filters.llm_filter._call_llm", return_value=response):
        result = llm_dedup([article, official, other])

    assert result == [official, other]
    assert _facts(official) == original
    assert official.alternate_urls == [article.url]


def test_dedup_can_select_an_existing_title_but_cannot_invent_url_or_other_facts():
    article = _event("News headline", "2026-11-20")
    article.url = "https://example.com/news"
    official = _event("Official hackathon title")
    original = _facts(article)
    response = json.dumps([{
        "group": [0, 1],
        "best_title": official.title,
        "best_url": "https://invented.example/hackathon",
        "description": "Invented description",
        "event_date": "2026-12-01",
    }])

    with patch("filters.llm_filter.config.GROQ_API_KEY", "test-key"), \
         patch("filters.llm_filter._call_llm", return_value=response):
        result = llm_dedup([article, official])

    assert result == [article]
    assert _facts(article) == {**original, "title": official.title}
    assert article.alternate_urls == [official.url]


@pytest.mark.parametrize("options", [[], ["--dry-run"]])
@pytest.mark.parametrize("as_mapping", [False, True])
def test_date_utility_is_read_only_even_when_month_is_available(tmp_path, caplog, options, as_mapping):
    events = [
        {"title": "Month only", "url": "https://example.com/month", "description": "May 2027", "date_str": ""},
        {"title": "Known date", "url": "https://example.com/known", "date_str": "2026-11-20"},
    ]
    archive = tmp_path / "events.json"
    archive.write_text(json.dumps({
        "last_check": "2026-10-10T08:00:00Z",
        "events": {str(i): event for i, event in enumerate(events)} if as_mapping else events,
    }))
    original = archive.read_bytes()

    with caplog.at_level(logging.INFO, logger="extract-dates"):
        status = audit_dates(["--events-file", str(archive), *options])

    assert status == 0
    assert "Eventi senza data: 1/2" in caplog.text
    assert "Month only" in caplog.text
    assert "Known date" not in caplog.text
    assert archive.read_bytes() == original
    assert list(tmp_path.iterdir()) == [archive]


@pytest.mark.parametrize("payload", ["invalid JSON", '{"events": [null]}', '{"events": "invalid"}'])
def test_date_utility_reports_invalid_archive_without_writing(tmp_path, payload):
    archive = tmp_path / "events.json"
    archive.write_text(payload)

    assert audit_dates(["--events-file", str(archive)]) == 1
    assert archive.read_text() == payload
