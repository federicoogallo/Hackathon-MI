"""Discovery contracts from observed source markup; no live network calls."""

import json
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from collectors.luma import LumaCollector
from collectors.universities import UniversitiesCollector
from collectors.web_search import WebSearchCollector, build_search_queries, evidence_candidates
from models import HackathonEvent
from utils import event_evidence
from utils.collector_health import track_collector


BOCCONI_CARDS = """
<article class="node node--internal-page">
  <h2>Today's Events</h2>
  <article class="bds-component-event-card">
    <a href="../events/ai-accessibility">
      <div class="bds-component-event-card__date-el">26 Sep 2026</div>
      <div class="bds-component-event-card__date-el">9:00am - 8:00pm</div>
      <div class="bds-component-event-card__title">AI Accessibility Hackathon</div>
      <div class="bds-component-event-card__location">Talent Garden, Milano</div>
    </a>
  </article>
  <article class="c-event-highlight-card bds-event-card-basic">
    <div class="bds-event-card-basic__title">Campus event in Chicago</div>
    <div class="bds-event-card-basic__date-el">13 Oct 2026</div>
    <div class="bds-event-card-basic__location">Chicago, USA</div>
    <div class="bds-event-card-basic__abstract"><p>Campus information.</p></div>
    <a href="/en/events/chicago">Read more</a>
  </article>
</article>
"""


def _response(html, url="https://www.unibocconi.it/en/news-and-events-hub/events"):
    response = MagicMock()
    response.text = html
    response.url = url
    return response


def test_bocconi_div_titles_do_not_become_outer_section_headings():
    events = UniversitiesCollector()._extract_events(
        BOCCONI_CARDS, "https://www.unibocconi.it/en/news-and-events-hub/events",
        "unibocconi.it", "Università Bocconi", set(),
    )
    assert [event.title for event in events] == ["AI Accessibility Hackathon", "Campus event in Chicago"]
    assert events[0].date_str == "26 Sep 2026"
    assert events[0].date_source == "event_card"
    assert events[0].location == "Talent Garden, Milano"
    assert events[0].url == "https://www.unibocconi.it/en/events/ai-accessibility"
    assert events[1].location == "Chicago, USA"


@patch("collectors.universities.safe_get")
def test_university_relative_urls_use_redirect_destination(mock_get):
    mock_get.return_value = _response(
        '<article><h3>Hackathon</h3><a href="../hackathon">Details</a></article>',
        "https://www.eventi.polimi.it/en/agenda/",
    )
    events = UniversitiesCollector()._collect_polimi()
    assert len(events) == 1
    assert events[0].url == "https://www.eventi.polimi.it/en/hackathon"


def test_luma_unknown_json_schema_uses_html_fallback():
    html = '<script id="__NEXT_DATA__">{"props":{"pageProps":{"newShape":true}}}</script>'
    html += '<a href="https://luma.com/bocconi-hackathon">Bocconi Hackathon Milano</a>'
    with patch("collectors.luma.safe_get", return_value=_response(html)):
        events = LumaCollector().collect()
    assert len(events) == 1
    assert events[0].url == "https://luma.com/bocconi-hackathon"


def test_luma_known_empty_event_list_does_not_fallback_to_navigation():
    html = '<script id="__NEXT_DATA__">{"props":{"pageProps":{"events":[]}}}</script>'
    html += '<a href="/profile">Some organizer</a>'
    with patch("collectors.luma.safe_get", return_value=_response(html)):
        assert LumaCollector().collect() == []


def test_luma_does_not_mistake_host_list_for_events():
    data = {"props": {"pageProps": {"initialData": {"hosts": [{"name": "Organizer"}], "events": [
        {"event": {"name": "AI Accessibility Hackathon", "url": "bainsa", "start_at": "2026-09-26T09:00:00+02:00",
                   "geo_address_info": {"city_state": "Milano, MI"}}},
    ]}}}}
    html = '<script id="__NEXT_DATA__">' + json.dumps(data) + '</script>'
    events = LumaCollector()._extract_from_next_data(html)
    assert len(events) == 1
    assert events[0].title == "AI Accessibility Hackathon"
    assert events[0].location == "Milano, MI"
    assert events[0].date_source == "event_api"


def test_luma_end_without_start_does_not_invent_event_start():
    event = LumaCollector()._parse_luma_event({"name": "Hackathon", "url": "test", "end_at": "2026-09-26"})
    assert event.date_str == event.date_source == ""


def test_luma_unrecognized_page_reports_parse_failure():
    with patch("collectors.luma.safe_get", return_value=_response("<html><p>New site shell</p></html>")):
        with track_collector() as health:
            assert LumaCollector().collect() == []
    assert health.issues[0]["kind"] == "parse_error"


def test_luma_html_fallback_checks_hosts_and_absolute_navigation():
    html = '''<a href="https://luma.com.attacker.test/hackathon">Fake hackathon</a>
    <a href="https://luma.com/signup">Create an account</a>
    <a href="https://lu.ma/bainsa">AI Accessibility Hackathon</a>'''
    events = LumaCollector()._extract_from_html(html)
    assert [event.url for event in events] == ["https://lu.ma/bainsa"]


def test_queries_roll_forward_and_cover_both_luma_domains_and_communities():
    queries = build_search_queries(date(2027, 1, 1))
    assert "hackathon Milano 2027" in queries
    assert "hackathon Milano 2028" in queries
    assert not any("2026" in query for query in queries)
    assert any("BAINSA" in query for query in queries)
    assert any("site:unibocconi.it" in query for query in queries)
    assert any("site:luma.com" in query for query in queries)
    assert any("site:lu.ma" in query for query in queries)


def test_web_search_evidence_budget_is_bounded():
    events = [HackathonEvent(title=f"Hackathon Milano {index}", url=f"https://luma.com/{index}", source="web_search") for index in range(30)]
    with patch("collectors.web_search.build_search_queries", return_value=["hackathon Milano"]), \
         patch.object(WebSearchCollector, "_search", return_value=events), \
         patch("collectors.web_search.enrich_event_evidence", return_value=True) as enrich:
        assert WebSearchCollector().collect() == events
    assert enrich.call_count == 8


def test_evidence_budget_rotates_daily_and_reserves_community_candidates():
    events = [HackathonEvent(title=f"Hackathon Milano {index}", url=f"https://luma.com/{index}", source="web_search") for index in range(30)]
    community = HackathonEvent(title="BAINSA AI Accessibility Hackathon", url="https://luma.com/zz-bainsa", source="web_search")
    events.append(community)
    first = evidence_candidates(events, date(2026, 9, 20))
    second = evidence_candidates(events, date(2026, 9, 21))
    assert len(first) == len(second) == 8
    assert community in first and community in second
    assert first == evidence_candidates(list(reversed(events)), date(2026, 9, 20))
    assert first != second


def test_unknown_host_stays_a_search_candidate_without_being_fetched():
    event = HackathonEvent(title="Hackathon Milano", url="https://unknown.example/hackathon", source="web_search")
    assert not event_evidence.is_promising_result(event)
    with patch("utils.event_evidence.socket.getaddrinfo") as dns:
        assert not event_evidence._public_url(event.url)
        dns.assert_not_called()


def _event():
    return HackathonEvent(title="AI Accessibility Hackathon", url="https://example.com/hackathon", source="web_search")


def test_event_date_is_separate_from_article_publication_date():
    # A retrospective fixture, not evidence of pre-event discovery or source HTML.
    html = '''<html><head><meta property="article:published_time" content="2026-09-28T09:00:00+02:00"></head>
    <body><article><h1>AI Accessibility Hackathon</h1><p>BAINSA and Anthropic brought builders to Talent Garden Milano on 26 September 2026.</p></article></body></html>'''
    event = _event()
    assert event_evidence.enrich_from_html(event, html)
    assert event.published_at == "2026-09-28T09:00:00+02:00"
    assert event.date_str == ""
    assert event.date_source == ""
    assert "26 September 2026" in event.description


def test_explicit_event_jsonld_preserves_bainsa_date_and_venue():
    event = _event()
    data = {"@context": "https://schema.org", "@type": "Event", "name": event.title,
            "startDate": "2026-09-26T09:00:00+02:00", "endDate": "2026-09-26T20:00:00+02:00",
            "location": {"@type": "Place", "name": "Talent Garden", "address": {"addressLocality": "Milano"}},
            "description": "BAINSA and Anthropic: AI Accessibility Hackathon."}
    html = '<script type="application/ld+json">' + json.dumps(data) + '</script>'
    assert event_evidence.enrich_from_html(event, html)
    assert event.parsed_date() == date(2026, 9, 26)
    assert event.is_upcoming(date(2026, 9, 20))
    assert event.date_source == "event_jsonld"
    assert event.location == "Talent Garden, Milano"


def test_event_listing_does_not_assign_an_unrelated_event_date():
    event = _event()
    data = [{"@type": "Event", "url": f"https://example.com/event-{index}", "startDate": "2027-01-12"} for index in range(2)]
    html = '<script type="application/ld+json">' + json.dumps(data) + '</script>'
    event_evidence.enrich_from_html(event, html)
    assert event.date_str == ""


def test_single_unrelated_embedded_event_does_not_assign_facts():
    event = HackathonEvent(title="PoliHack 2026", url="https://example.com/articles/polihack", source="web_search")
    data = {"@type": "Event", "name": "Different conference", "url": "https://elsewhere.example/conference", "startDate": "2026-11-02", "location": "Milano"}
    html = '<script type="application/ld+json">' + json.dumps(data) + '</script>'
    assert not event_evidence.enrich_from_html(event, html)
    assert event.date_str == event.location == event.date_source == ""


def test_single_event_with_wrong_edition_does_not_override_candidate():
    event = HackathonEvent(title="PoliHack 2026", url="https://example.com/polihack", source="web_search")
    data = {"@type": "Event", "name": "PoliHack 2027", "url": event.url, "startDate": "2027-11-02"}
    html = '<script type="application/ld+json">' + json.dumps(data) + '</script>'
    event_evidence.enrich_from_html(event, html)
    assert event.date_str == ""


def test_multiple_events_require_one_unambiguous_identity_match():
    event = _event()
    matching = {"@type": "Event", "name": event.title, "url": event.url, "startDate": "2026-09-26"}
    other = {"@type": "Event", "name": "Different conference", "url": "https://example.com/other", "startDate": "2026-11-02"}
    html = '<script type="application/ld+json">' + json.dumps([other, matching]) + '</script>'
    assert event_evidence.enrich_from_html(event, html)
    assert event.date_str == "2026-09-26"
    ambiguous = _event()
    conflicting = {**matching, "startDate": "2026-10-02"}
    html = '<script type="application/ld+json">' + json.dumps([matching, conflicting]) + '</script>'
    event_evidence.enrich_from_html(ambiguous, html)
    assert ambiguous.date_str == ""


def test_luma_alias_binds_jsonld_to_the_search_event():
    event = HackathonEvent(title="AI Accessibility Hackathon", url="https://lu.ma/bainsa", source="web_search")
    data = {"@type": "Event", "url": "https://luma.com/bainsa", "startDate": "2026-09-26"}
    html = '<script type="application/ld+json">' + json.dumps(data) + '</script>'
    assert event_evidence.enrich_from_html(event, html)
    assert event.date_str == "2026-09-26"


def test_malformed_jsonld_does_not_break_useful_page_evidence():
    html = '''<body><script type="application/ld+json">not json</script>
    <script type="application/ld+json">{"@type":null,"name":"Unrelated object"}</script>
    <main><p>AI Accessibility Hackathon, BAINSA, Talent Garden Milano.</p></main></body>'''
    event = _event()
    assert event_evidence.enrich_from_html(event, html)
    assert "Talent Garden Milano" in event.description
    assert event.date_str == ""


def test_antibot_page_is_not_saved_as_event_evidence():
    event = _event()
    assert not event_evidence.enrich_from_html(event, '<html><title>Just a moment...</title><body><p>Hackathon Milano request blocked.</p></body></html>')
    assert event.description == ""


@pytest.mark.parametrize("url", ["http://localhost/hack", "http://127.0.0.1/hack", "http://10.0.0.1/hack", "http://[::1]/hack", "file:///tmp/hack", "https://user:password@example.com/hack", "http://example.com:8080/hack"])
def test_evidence_fetch_rejects_nonpublic_destinations(url):
    with patch("utils.event_evidence.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 80))]):
        assert not event_evidence._public_url(url)


def test_public_hostname_must_not_resolve_to_any_private_address():
    addresses = [(2, 1, 6, "", ("93.184.216.34", 443)), (2, 1, 6, "", ("127.0.0.1", 443))]
    with patch("utils.event_evidence.socket.getaddrinfo", return_value=addresses):
        assert not event_evidence._public_url("https://luma.com/hackathon")


def _http_response(status=200, content_type="text/html", chunks=None, location=""):
    response = MagicMock()
    response.__enter__.return_value = response
    response.status_code = status
    response.headers = {"Content-Type": content_type, "Location": location}
    response.encoding = "utf-8"
    response.iter_content.return_value = chunks or [b"<html>Hackathon</html>"]
    return response


@pytest.mark.parametrize("status", [401, 403, 429, 503])
def test_evidence_fetch_does_not_retry_or_bypass_denied_pages(status):
    with patch("utils.event_evidence._public_url", return_value=True), patch("utils.event_evidence.requests.Session") as session:
        client = session.return_value.__enter__.return_value
        response = _http_response(status=status)
        client.get.return_value = response
        assert event_evidence.fetch_public_html("https://example.com/hackathon") is None
        client.get.assert_called_once()
        response.iter_content.assert_not_called()


def test_evidence_fetch_blocks_redirect_to_private_host():
    with patch("utils.event_evidence._public_url", side_effect=[True, False]), patch("utils.event_evidence.requests.Session") as session:
        client = session.return_value.__enter__.return_value
        client.get.return_value = _http_response(status=302, location="http://127.0.0.1/private")
        assert event_evidence.fetch_public_html("https://example.com/hackathon") is None
        client.get.assert_called_once()


def test_evidence_fetch_enforces_body_limit():
    with patch("utils.event_evidence._public_url", return_value=True), patch("utils.event_evidence.requests.Session") as session, patch("utils.event_evidence.MAX_PAGE_BYTES", 10):
        client = session.return_value.__enter__.return_value
        client.get.return_value = _http_response(chunks=[b"a" * 11])
        assert event_evidence.fetch_public_html("https://example.com/hackathon") is None
