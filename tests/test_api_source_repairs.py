"""Official API contracts, publication safety and diagnostics without network access."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import config
from collectors import eventbrite, reddit
from utils.collector_health import track_collector


@pytest.fixture
def eventbrite_api(monkeypatch):
    monkeypatch.setattr(config, "EVENTBRITE_API_KEY", "test-secret")
    monkeypatch.setattr(config, "EVENTBRITE_ORGANIZATION_IDS", ["123"])
    request = MagicMock()
    monkeypatch.setattr(eventbrite, "safe_get_json", request)
    return request


def public_event(**changes):
    item = {
        "name": {"text": "Milano Accessibility Hackathon"},
        "url": "https://www.eventbrite.it/e/hackathon-123",
        "listed": True, "status": "live",
        "summary": "An accessible technology challenge",
        "start": {"local": "2026-12-11T09:00:00"},
        "end": {"local": "2026-12-12T18:00:00"},
        "published": "2026-10-12T10:00:00Z",
        "venue": {"address": {"localized_address_display": "Milano, Italia"}},
        "organizer": {"name": "Local community"},
    }
    item.update(changes)
    return item


def test_eventbrite_does_not_request_retired_global_search(eventbrite_api, monkeypatch):
    monkeypatch.setattr(config, "EVENTBRITE_ORGANIZATION_IDS", [])
    with track_collector() as health:
        assert eventbrite.EventbriteCollector().collect() == []
    eventbrite_api.assert_not_called()
    assert health.outcome(0) == "disabled"
    assert "Global event search retired" in health.issues[0]["detail"]


@pytest.mark.parametrize("ids", [["123/../../users"], [12], "123", ["123?secret"]])
def test_eventbrite_rejects_invalid_organization_ids(eventbrite_api, monkeypatch, ids):
    monkeypatch.setattr(config, "EVENTBRITE_ORGANIZATION_IDS", ids)
    with track_collector() as health:
        assert eventbrite.EventbriteCollector().collect() == []
    eventbrite_api.assert_not_called()
    assert health.issues[0]["kind"] == "configuration_error"
    assert "test-secret" not in json.dumps(health.issues)


def test_eventbrite_uses_organization_endpoint_and_continuation(eventbrite_api):
    eventbrite_api.side_effect = [
        {"events": [public_event()], "pagination": {"has_more_items": True, "continuation": "next"}},
        {"events": [public_event(), public_event(url="https://www.eventbrite.it/e/second-456")],
         "pagination": {"has_more_items": False}},
    ]
    results = eventbrite.EventbriteCollector().collect()
    assert len(results) == 2
    first, second = eventbrite_api.call_args_list
    assert first.args[0] == "https://www.eventbriteapi.com/v3/organizations/123/events/"
    assert first.kwargs["params"]["status"] == "live"
    assert first.kwargs["params"]["time_filter"] == "current_future"
    assert second.kwargs["params"]["continuation"] == "next"
    assert "page" not in second.kwargs["params"]
    assert results[0].date_source == "event_api"
    assert results[0].published_at == "2026-10-12T10:00:00Z"
    assert results[0].location == "Milano, Italia"


@pytest.mark.parametrize("changes", [
    {"listed": False}, {"listed": "true"}, {"listed": None},
    {"status": "draft"}, {"status": "canceled"}, {"status": "ended"},
    {"invite_only": True}, {"password": "secret"}, {"is_series_parent": True},
])
def test_eventbrite_never_publishes_private_or_inactive_records(eventbrite_api, changes):
    eventbrite_api.return_value = {"events": [public_event(**changes)], "pagination": {"has_more_items": False}}
    assert eventbrite.EventbriteCollector().collect() == []


def test_eventbrite_respects_hidden_dates_and_does_not_promote_publication_date():
    collector = eventbrite.EventbriteCollector()
    hidden = collector._parse_event(public_event(hide_start_date=True))
    assert hidden.date_str == ""
    assert hidden.date_source == "unknown"
    assert not hidden.has_event_date
    assert hidden.published_at
    assert collector._parse_event(public_event(hide_end_date=True)).date_str == "2026-12-11T09:00:00"
    assert collector._parse_event(public_event(start=None)).date_str == ""


def test_eventbrite_repeated_continuation_and_page_limit_are_not_silent(eventbrite_api, monkeypatch):
    eventbrite_api.return_value = {"events": [public_event()], "pagination": {"has_more_items": True, "continuation": "same"}}
    with track_collector() as health:
        events = eventbrite.EventbriteCollector().collect()
    assert len(events) == 1
    assert eventbrite_api.call_count == 2
    assert health.outcome(len(events)) == "degraded"
    assert health.issues[0]["kind"] == "parse_error"
    eventbrite_api.reset_mock()
    eventbrite_api.return_value = {"events": [public_event()], "pagination": {"page_count": 10}}
    with track_collector() as health:
        assert len(eventbrite.EventbriteCollector().collect()) == 1
    assert eventbrite_api.call_count == eventbrite.MAX_PAGES
    assert health.issues[0]["kind"] == "pagination_limit"


@pytest.mark.parametrize("payload", [{}, {"events": None}, {"events": {"id": 1}}, []])
def test_eventbrite_invalid_schema_is_reported(eventbrite_api, payload):
    eventbrite_api.return_value = payload
    with track_collector() as health:
        assert eventbrite.EventbriteCollector().collect() == []
    assert health.issues[0]["kind"] == "parse_error"


def test_eventbrite_null_optional_objects_do_not_discard_public_event():
    result = eventbrite.EventbriteCollector()._parse_event(public_event(
        summary=None, description=None, start=None, end=None, venue=None, organizer=None,
    ))
    assert result is not None
    assert result.description == result.location == result.organizer == result.date_str == ""


@pytest.fixture
def reddit_api(monkeypatch):
    monkeypatch.setattr(config, "REDDIT_CLIENT_ID", "test-id")
    monkeypatch.setattr(config, "REDDIT_CLIENT_SECRET", "test-secret")
    monkeypatch.setattr(config, "REDDIT_USER_AGENT", "script:community-monitor:v1 (by /u/actual-owner)")
    monkeypatch.setattr(reddit, "_PRAW_AVAILABLE", True)
    client = MagicMock()
    client.subreddit.return_value.search.return_value = []
    constructor = MagicMock(return_value=client)
    monkeypatch.setattr(reddit, "praw", SimpleNamespace(Reddit=constructor))
    return client, constructor


def submission(**changes):
    item = {"title": "Accessibility Hackathon Milano", "url": "https://example.org/hackathon",
            "selftext": "A new hackathon", "created_utc": 1791792000,
            "permalink": "/r/ItalyInformatica/comments/example/hackathon/"}
    item.update(changes)
    return SimpleNamespace(**item)


def test_reddit_requires_actual_user_agent_and_never_invents_bot_identity(reddit_api, monkeypatch):
    client, constructor = reddit_api
    monkeypatch.setattr(config, "REDDIT_USER_AGENT", "")
    with track_collector() as health:
        assert reddit.RedditCollector().collect() == []
    constructor.assert_not_called()
    assert health.outcome(0) == "disabled"
    assert "REDDIT_USER_AGENT" in health.issues[0]["detail"]


def test_reddit_empty_completed_reads_are_healthy_and_readonly(reddit_api):
    client, constructor = reddit_api
    with track_collector() as health:
        assert reddit.RedditCollector().collect() == []
    assert health.outcome(0) == "empty"
    assert health.requests_ok == len(reddit.SUBREDDITS) * len(reddit.SEARCH_QUERIES)
    assert client.read_only is True
    assert constructor.call_args.kwargs["user_agent"] == config.REDDIT_USER_AGENT


def test_reddit_deduplicates_and_keeps_post_date_separate(reddit_api):
    client, _ = reddit_api
    client.subreddit.return_value.search.return_value = [submission(), submission(url="https://example.org/hackathon?utm_source=reddit")]
    events = reddit.RedditCollector().collect()
    assert len(events) == 1
    assert events[0].published_at
    assert events[0].date_str == ""
    assert not events[0].has_event_date


@pytest.mark.parametrize("status", [401, 403, 429])
def test_reddit_access_blocks_stop_queries_and_do_not_log_credentials(reddit_api, status, caplog):
    client, _ = reddit_api
    error = RuntimeError("private test-secret test-id")
    error.response = SimpleNamespace(status_code=status)
    client.subreddit.return_value.search.side_effect = error
    with track_collector() as health:
        assert reddit.RedditCollector().collect() == []
    assert client.subreddit.call_count == 1
    assert client.subreddit.return_value.search.call_count == 1
    assert health.outcome(0) == "blocked"
    assert "test-secret" not in caplog.text + json.dumps(health.issues)


def test_reddit_partial_iteration_failure_retains_records(reddit_api):
    client, _ = reddit_api
    def partial_results():
        yield submission()
        error = RuntimeError("denied")
        error.response = SimpleNamespace(status_code=403)
        raise error
    client.subreddit.return_value.search.return_value = partial_results()
    with track_collector() as health:
        events = reddit.RedditCollector().collect()
    assert len(events) == 1
    assert health.outcome(len(events)) == "degraded"
    assert health.requests_ok == 0


def test_reddit_selfpost_canonical_url_does_not_replace_lookalike_hosts():
    collector = reddit.RedditCollector()
    selfpost = collector._parse_submission(submission(url="https://old.reddit.com/r/ItalyInformatica/comments/example/hackathon/"), "ItalyInformatica")
    assert selfpost.url == "https://www.reddit.com/r/ItalyInformatica/comments/example/hackathon/"
    external = collector._parse_submission(submission(url="https://not-reddit.com/hackathon"), "ItalyInformatica")
    assert external.url == "https://not-reddit.com/hackathon"
