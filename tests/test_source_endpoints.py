"""Regression fixtures for official source endpoints verified on 2026-10-11."""

import json
from types import SimpleNamespace
from unittest.mock import patch

from collectors.talent_garden import TALENT_GARDEN_URLS, TalentGardenCollector
from collectors.telespazio import TELESPAZIO_INDEX_URLS, TelespazioCollector


def agenda_row(**overrides):
    return {
        "event_name": "Bocconi AI Hackathon",
        "url": "https://www.eventbrite.com/e/example-123",
        "description": "<p>Build AI prototypes at this hackathon in Milano.</p>",
        "start_utc": "2026-11-20T08:00:00Z",
        "end_utc": "2026-11-21T18:00:00Z",
        "created_at": "2026-10-01T12:00:00Z",
        "status": "live",
        "venue_info": {"localized_address_display": "Via Calabiana 6, Milano"},
        "organizer_name": "Talent Garden",
        "online_event": False,
        **overrides,
    }


def agenda_html(rows):
    data = [{"moduleName": "Slider", "props": {"variant": "variant-events", "data": rows}}]
    return f"<html><script>var newIslands = {json.dumps(data)}; unrelatedJavascript();</script></html>"


def test_talent_garden_collects_public_agenda_data_from_current_endpoint():
    with patch("collectors.talent_garden.safe_get", return_value=SimpleNamespace(text=agenda_html([agenda_row()]))) as fetch:
        events = TalentGardenCollector().collect()
    assert TALENT_GARDEN_URLS == ["https://talentgarden.com/it/agenda"]
    fetch.assert_called_once_with("https://talentgarden.com/it/agenda")
    assert len(events) == 1
    event = events[0]
    assert event.title == "Bocconi AI Hackathon"
    assert event.date_str == "2026-11-20T08:00:00Z — 2026-11-21T18:00:00Z"
    assert event.date_source == "event_api"
    assert event.location == "Via Calabiana 6, Milano"
    assert "<p>" not in event.description
    assert event.published_at == ""


def test_talent_garden_deduplicates_public_modules_and_ignores_cancelled_rows():
    rows = [agenda_row(), agenda_row(), agenda_row(url="https://example.org/cancelled", status="cancelled")]
    events = TalentGardenCollector()._parse_html(agenda_html(rows), TALENT_GARDEN_URLS[0], set())
    assert len(events) == 1


def test_talent_garden_explicit_online_event_does_not_inherit_physical_venue():
    events = TalentGardenCollector()._parse_html(agenda_html([agenda_row(online_event=True)]), TALENT_GARDEN_URLS[0], set())
    assert events[0].location == "Online"


def test_talent_garden_missing_event_start_is_not_filled_from_created_at():
    events = TalentGardenCollector()._parse_html(agenda_html([agenda_row(start_utc=None)]), TALENT_GARDEN_URLS[0], set())
    assert events[0].date_str == ""
    assert events[0].date_source == "unknown"


def test_talent_garden_ignores_non_event_islands_and_malformed_payloads():
    html = '<script>var newIslands = notValidJSON;</script>'
    html += '<script>var newIslands = [{"moduleName":"NavigationMenuV2", "props":{}}];</script>'
    assert TalentGardenCollector()._parse_html(html, TALENT_GARDEN_URLS[0], set()) == []


def test_telespazio_visits_current_news_indexes_and_retains_careers():
    with patch("collectors.telespazio.safe_get", return_value=SimpleNamespace(text="<html></html>")) as fetch:
        assert TelespazioCollector().collect() == []
    assert {call.args[0] for call in fetch.call_args_list} == {
        "https://www.telespazio.com/en/careers",
        "https://www.telespazio.com/en/media-hub/news-stories",
        "https://www.telespazio.com/it/media-hub/news-storie",
    }


def test_telespazio_publication_and_footer_address_are_not_event_facts():
    html = '''<html><head><meta property="article:published_time" content="2026-10-01T10:00:00Z"></head>
      <body><main><h1>Space Hackathon</h1><p>Hackathon applications open soon; details to follow.</p></main>
      <footer>Published 1 October 2026. Our legal partner is established in Milan.</footer></body></html>'''
    with patch("collectors.telespazio.safe_get", return_value=SimpleNamespace(text=html)):
        event = TelespazioCollector()._collect_detail("https://www.telespazio.com/en/hackathon")
    assert event.published_at == "2026-10-01T10:00:00Z"
    assert event.date_str == ""
    assert event.location == ""
    assert "legal partner" not in event.description


def test_telespazio_uses_explicit_event_jsonld_dates_and_venue():
    data = {"@type": "Event", "name": "Space Hackathon", "startDate": "2026-11-20", "location": {"name": "Campus Milano"}}
    html = f'<html><h1>Space Hackathon</h1><script type="application/ld+json">{json.dumps(data)}</script></html>'
    with patch("collectors.telespazio.safe_get", return_value=SimpleNamespace(text=html)):
        event = TelespazioCollector()._collect_detail("https://www.telespazio.com/en/hackathon")
    assert event.date_str == "2026-11-20"
    assert event.date_source == "event_jsonld"
    assert event.location == "Campus Milano"


def test_telespazio_preserves_prose_dates_for_review_without_guessing_event_start():
    html = '<html><main><h1>Space Hackathon</h1><p>The hackathon takes place on 20 November 2026 in Milan.</p></main></html>'
    with patch("collectors.telespazio.safe_get", return_value=SimpleNamespace(text=html)):
        event = TelespazioCollector()._collect_detail("https://www.telespazio.com/en/hackathon")
    assert event.date_str == ""
    assert "20 November 2026 in Milan" in event.description


def test_telespazio_detail_discovery_accepts_only_official_hosts():
    html = '''<a href="/en/careers/hackathon">Space Hackathon</a>
      <a href="https://telespazio.com.evil.example/hackathon">Hackathon</a>
      <a href="https://eviltelespazio.com/hackathon">Hackathon</a>'''
    urls = TelespazioCollector()._extract_detail_urls(html, TELESPAZIO_INDEX_URLS[0])
    assert urls == {"https://www.telespazio.com/en/careers/hackathon"}
