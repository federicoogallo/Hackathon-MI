"""Contracts from the platforms' public catalogue responses; no network calls."""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from collectors.challengerocket import ChallengeRocketCollector, CHALLENGEROCKET_URLS
from collectors.devpost import DevpostCollector, DEVPOST_API_URL
from collectors.dorahacks import DoraHacksCollector, DORAHACKS_URL
from collectors.eventbrite_web import EventbriteWebCollector, EVENTBRITE_URLS
from collectors.hackerearth import HackerEarthCollector, HACKEREARTH_API_URL
from collectors.startup_italia import StartupItaliaCollector, RSS_URLS, STARTUP_ITALIA_URLS
from utils.collector_health import track_collector, record_issue


def response(payload):
    return SimpleNamespace(text=json.dumps(payload) if not isinstance(payload, str) else payload, status_code=200)


def devpost_item(**extra):
    return {"title": "Milano AI Hackathon", "url": "https://milano-ai.devpost.com/",
            "displayed_location": {"location": "Milano"}, "organization_name": "University",
            "submission_period_dates": "Oct 20 - 23, 2026", "themes": [{"name": "AI"}], **extra}


def test_devpost_reads_api_and_deduplicates_queries():
    data = {"hackathons": [devpost_item()], "meta": {"total_count": 1, "per_page": 9, "fuzzy": False}}
    with patch("collectors.devpost.safe_get", return_value=response(data)) as fetch:
        events = DevpostCollector().collect()
    assert len(events) == 1
    assert all(call.args[0] == DEVPOST_API_URL for call in fetch.call_args_list)
    assert events[0].location == "Milano"
    assert events[0].date_source == "deadline"
    assert not events[0].has_event_date
    assert "Oct 20 - 23, 2026" in events[0].description


def test_devpost_fuzzy_suggestions_are_not_local_matches():
    item = devpost_item(title="MLAI 2026", displayed_location={"location": "Online"})
    assert DevpostCollector()._parse_api_item(item, set(), fuzzy=True) is None
    assert DevpostCollector()._parse_api_item(devpost_item(), set(), fuzzy=True) is not None


def test_devpost_paginates_bounded_results():
    first = {"hackathons": [devpost_item()], "meta": {"total_count": 10, "per_page": 9}}
    last = {"hackathons": [], "meta": {"total_count": 10, "per_page": 9}}
    with patch("collectors.devpost.DEVPOST_QUERIES", ("milan",)), patch(
        "collectors.devpost.safe_get", side_effect=[response(first), response(last)]
    ) as fetch:
        assert len(DevpostCollector().collect()) == 1
    assert [call.kwargs["params"]["page"] for call in fetch.call_args_list] == [1, 2]


@pytest.mark.parametrize("payload", [{"unexpected": []}, "<html>blocked</html>", {"hackathons": None}])
def test_devpost_schema_failures_reported(payload):
    with patch("collectors.devpost.safe_get", return_value=response(payload)), track_collector() as health:
        assert DevpostCollector().collect() == []
    assert health.issues and all(issue["kind"] == "parse_error" for issue in health.issues)


def rocket_card(title, category, path):
    return f'''<div class="seo-link challenge-card"><div class="challenge-card__image"><a href="/wrong">Image</a></div>
    <div class="challenge-card__title"><a href="{path}">{title}</a></div>
    <div class="challenge-card__feature-list-item"><div class="challenge-card__feature-list-label">Category</div>
    <div class="challenge-card__feature-list-value">{category}</div></div></div>'''


def test_rocket_uses_real_card_titles_and_skips_recruiting_quizzes():
    html = '<a href="/run-outstanding-hackathons">Hackathons</a>' + rocket_card("CASSINI Hackathon", "Online Creative Challenge", "/cassini")
    html += rocket_card("AI architect", "Multiple-Choice", "/ai-test")
    events = ChallengeRocketCollector()._parse_html(html, set())
    assert len(events) == 1
    assert events[0].url == "https://challengerocket.com/cassini"
    assert events[0].location == "Online"
    assert events[0].date_str == ""
    assert CHALLENGEROCKET_URLS == ["https://challengerocket.com/hackathons-and-challenges.html"]


def test_rocket_does_not_label_missing_markup_as_empty_success():
    with track_collector() as health:
        assert ChallengeRocketCollector()._parse_html("<html>New layout</html>", set()) == []
    assert health.issues[0]["kind"] == "parse_error"


def test_hackerearth_reads_current_compete_schema_without_inventing_a_city():
    item = {"title": "Milano Hackathon", "type": "Hackathon", "url": "/challenges/hackathon/milano/",
            "start": "2026-11-01T10:00:00", "end": "2026-11-02T10:00:00", "company_name": "Company"}
    other = {"title": "Java recruiting test", "type": "Hiring", "url": "/challenges/hiring/test/"}
    with patch("collectors.hackerearth.safe_get_json", return_value={"data": [item, item, other]}) as fetch:
        events = HackerEarthCollector().collect()
    fetch.assert_called_once_with(HACKEREARTH_API_URL)
    assert len(events) == 1
    assert events[0].date_source == "event_api"
    assert events[0].location == ""
    assert events[0].organizer == "Company"
    assert events[0].url == "https://www.hackerearth.com/challenges/hackathon/milano/"


@pytest.mark.parametrize("payload,has_error", [({"data": []}, False), ({"newSchema": []}, True)])
def test_hackerearth_distinguishes_empty_and_changed_schema(payload, has_error):
    with patch("collectors.hackerearth.safe_get_json", return_value=payload), track_collector() as health:
        assert HackerEarthCollector().collect() == []
    assert bool(health.issues) == has_error


def test_startup_rss_publishes_editorial_date_separately_and_ignores_cyberattack_articles():
    rss = '''<rss><channel><item><title>Hackathon Milano</title><link>https://startupitalia.eu/hack</link>
    <pubDate>Wed, 14 Oct 2026 12:00:00 GMT</pubDate><description>Hackathon futuro</description></item>
    <item><title>Gli hacker attaccano un supermercato</title><link>https://startupitalia.eu/cyber</link></item></channel></rss>'''
    with patch("collectors.startup_italia.safe_get", return_value=response(rss)):
        events = StartupItaliaCollector()._collect_rss(RSS_URLS[0], set())
    assert len(events) == 1
    assert events[0].published_at == "Wed, 14 Oct 2026 12:00:00 GMT"
    assert events[0].date_str == ""
    assert "https://startupitalia.eu/tag/hackathon/feed/" in RSS_URLS
    assert all(url.endswith("/") for url in RSS_URLS + STARTUP_ITALIA_URLS)


def test_startup_html_prefers_title_link_over_category():
    from bs4 import BeautifulSoup
    html = '<article><a href="/tag/hackathon/">Tag</a><h2><a href="/new-hack/">Hackathon Milano</a></h2></article>'
    event = StartupItaliaCollector()._parse_card(BeautifulSoup(html, "lxml").article, "https://startupitalia.eu/", set())
    assert event.url == "https://startupitalia.eu/new-hack/"


def eventbrite_item():
    return {"@type": "Event", "name": "Hackathon Milano", "url": "https://www.eventbrite.com/e/hack-123",
            "startDate": "2026-11-01", "endDate": "2026-11-02", "location": {"address": {"addressLocality": "Milano"}}}


@pytest.mark.parametrize("wrapper", [lambda n: n, lambda n: [n], lambda n: {"@graph": [n]}])
def test_eventbrite_reads_itemlist_in_all_jsonld_envelopes(wrapper):
    data = wrapper({"@type": "ItemList", "itemListElement": [{"@type": "ListItem", "item": eventbrite_item()}]})
    html = '<script type="application/ld+json">[{"@type":"BreadcrumbList","itemListElement":[]}]</script>'
    html += f'<script type="application/ld+json">{json.dumps(data)}</script>'
    with patch("collectors.eventbrite_web.safe_get", return_value=response(html)):
        events = EventbriteWebCollector().collect()
    assert len(events) == 1
    assert events[0].date_source == "event_jsonld"
    assert events[0].location == "Milano"
    assert all("italy--milano" in url for url in EVENTBRITE_URLS)


@pytest.mark.parametrize("html,has_error", [('<script type="application/ld+json">{"@type":"ItemList","itemListElement":[]}</script>', False),
                                           ('<html>Loading...</html>', True)])
def test_eventbrite_distinguishes_empty_from_unreadable(html, has_error):
    with patch("collectors.eventbrite_web.safe_get", return_value=response(html)), track_collector() as health:
        assert EventbriteWebCollector().collect() == []
    assert bool(health.issues) == has_error


def test_dorahacks_uses_public_listing_and_keeps_access_denial_visible():
    def blocked(url):
        record_issue("blocked", "HTTP 405", url)
        return None
    with patch("collectors.dorahacks.safe_get", side_effect=blocked) as fetch, track_collector() as health:
        assert DoraHacksCollector().collect() == []
    fetch.assert_called_once_with(DORAHACKS_URL)
    assert health.outcome(0) == "blocked"


def test_dorahacks_unknown_markup_is_not_success():
    with patch("collectors.dorahacks.safe_get", return_value=response('<html>New app</html>')), track_collector() as health:
        assert DoraHacksCollector().collect() == []
    assert health.issues[0]["kind"] == "parse_error"


def test_dorahacks_never_invents_milan_from_missing_location():
    event = DoraHacksCollector()._parse_item({"name": "Hackathon", "url": "https://dorahacks.io/hackathon/test"}, set())
    assert event.location == ""


@pytest.mark.parametrize("start", [None, "", "   "])
def test_eventbrite_end_date_alone_is_evidence_not_start_date(start):
    item = eventbrite_item()
    item["startDate"] = start
    item["endDate"] = "2026-11-01"
    event = EventbriteWebCollector()._parse_item(item)
    assert event.date_str == ""
    assert not event.has_event_date
    assert event.parsed_date() is None
    assert "Fine evento indicata dalla fonte: 2026-11-01" in event.description


@pytest.mark.parametrize("source,collector", [("dorahacks", DoraHacksCollector), ("eventbrite_web", EventbriteWebCollector)])
@pytest.mark.parametrize("item", [{"@type": "Organization", "name": "Company"}, {"@type": "Event", "name": "Missing URL"}, "https://example.com/event"])
def test_nonempty_unreadable_itemlist_is_not_an_empty_success(source, collector, item):
    data = {"@type": "ItemList", "itemListElement": [{"@type": "ListItem", "item": item}]}
    html = f'<script type="application/ld+json">{json.dumps(data)}</script>'
    with patch(f"collectors.{source}.safe_get", return_value=response(html)), track_collector() as health:
        assert collector().collect() == []
    assert any(issue["kind"] == "parse_error" for issue in health.issues)
    assert health.outcome(0) != "empty"


@pytest.mark.parametrize("source,collector", [("dorahacks", DoraHacksCollector), ("eventbrite_web", EventbriteWebCollector)])
def test_empty_itemlist_does_not_hide_another_unreadable_list(source, collector):
    data = [{"@type": "ItemList", "itemListElement": []}, {"@type": "ItemList", "itemListElement": [{"@type": "Organization"}]}]
    html = f'<script type="application/ld+json">{json.dumps(data)}</script>'
    with patch(f"collectors.{source}.safe_get", return_value=response(html)), track_collector() as health:
        assert collector().collect() == []
    assert health.issues


def test_dorahacks_explicit_empty_list_is_valid_and_repeated_events_are_deduplicated():
    data = {"@type": "ItemList", "itemListElement": []}
    with patch("collectors.dorahacks.safe_get", return_value=response(f'<script type="application/ld+json">{json.dumps(data)}</script>')), track_collector() as health:
        assert DoraHacksCollector().collect() == []
    assert not health.issues
    item = {"@type": "Event", "name": "Hackathon Milano", "url": "https://dorahacks.io/hackathon/milano"}
    data["itemListElement"] = [{"@type": "ListItem", "item": item}, item]
    with patch("collectors.dorahacks.safe_get", return_value=response(f'<script type="application/ld+json">{json.dumps(data)}</script>')), track_collector() as health:
        assert len(DoraHacksCollector().collect()) == 1
    assert not health.issues


@pytest.mark.parametrize("content", [
    '<app-root>Please Wait</app-root><script src="main.js" type="module"></script>',
    '<div class="listing"><a href="https://unstop.com/legal/privacy-policy">Privacy Policy</a></div>',
    '<script type="application/json">{"data":[]}</script>',
    '<script type="application/json">[]</script>',
    '<script type="application/json">{"hackathons":[{"name":"Company","url":"/companies/company"}]}</script>',
])
def test_unstop_js_shell_and_unrelated_data_are_not_empty_success(content):
    from collectors.unstop import UnstopCollector
    with patch("collectors.unstop.safe_get", return_value=response(content)), track_collector() as health:
        assert UnstopCollector().collect() == []
    assert health.issues and all(issue["kind"] == "parse_error" for issue in health.issues)


def test_unstop_explicit_empty_api_catalogue_is_valid():
    from collectors.unstop import UnstopCollector
    with patch("collectors.unstop.safe_get", return_value=response({"data": {"data": [], "last_page": 1}})), track_collector() as health:
        assert UnstopCollector().collect() == []
    assert not health.issues


def unstop_item(**extra):
    return {"title": "Hackathon Milano", "public_url": "hackathons/milano-ai-123", "type": "hackathons",
            "region": "offline", "end_date": "2026-11-01",
            "address_with_country_logo": {"city": "Milano", "country": {"name": "Italy", "alpha_2": "it"}},
            "organisation": {"name": "University abroad"}, "details": "<p>Build an AI prototype.</p>", **extra}


def test_unstop_api_deduplicates_and_never_treats_closure_as_start():
    from collectors.unstop import UnstopCollector, UNSTOP_API_URL
    data = {"data": {"data": [unstop_item()], "last_page": 1}}
    with patch("collectors.unstop.safe_get", return_value=response(data)) as fetch, track_collector() as health:
        events = UnstopCollector().collect()
    assert len(events) == 1
    assert not events[0].has_event_date
    assert events[0].date_source == "deadline"
    assert events[0].location == "Milano, Italy"
    assert events[0].organizer == "University abroad"
    assert events[0].description == "Build an AI prototype."
    assert not health.issues
    assert all(call.args[0] == UNSTOP_API_URL for call in fetch.call_args_list)
    assert {call.kwargs["params"]["searchTerm"] for call in fetch.call_args_list} == {"milan", "milano", "italy"}


@pytest.mark.parametrize("item", [
    unstop_item(region="online"),
    unstop_item(address_with_country_logo={"city": "Ahmedabad", "country": {"alpha_2": "in"}}),
    unstop_item(address_with_country_logo={"city": "Milan", "country": {"name": "United States"}}),
])
def test_unstop_excludes_explicitly_foreign_and_online_venues_but_source_is_readable(item):
    from collectors.unstop import UnstopCollector
    with patch("collectors.unstop.safe_get", return_value=response({"data": {"data": [item], "last_page": 1}})), track_collector() as health:
        assert UnstopCollector().collect() == []
    assert not health.issues


def test_unstop_unknown_country_is_not_invented_or_rejected():
    from collectors.unstop import UnstopCollector
    item = unstop_item(address_with_country_logo={"city": "Milano"})
    assert UnstopCollector._in_scope(item)
    assert UnstopCollector()._parse_api_item(item).location == "Milano"


def test_unstop_paginates_without_following_response_urls():
    from collectors.unstop import UnstopCollector, UNSTOP_API_URL
    page_one = {"data": {"data": [unstop_item()], "last_page": 2, "next_page_url": "http://internal.invalid/"}}
    page_two = {"data": {"data": [unstop_item(title="Second", public_url="hackathons/second-456")], "last_page": 2}}
    with patch("collectors.unstop.UNSTOP_QUERIES", ("milan",)), patch("collectors.unstop.safe_get", side_effect=[response(page_one), response(page_two)]) as fetch:
        events = UnstopCollector().collect()
    assert len(events) == 2
    assert [call.kwargs["params"]["page"] for call in fetch.call_args_list] == [1, 2]
    assert all(call.args[0] == UNSTOP_API_URL for call in fetch.call_args_list)


@pytest.mark.parametrize("payload", [{"data": []}, {"data": {"data": [{"name": "Invalid"}]}}])
def test_unstop_api_schema_drift_is_reported(payload):
    from collectors.unstop import UnstopCollector
    with patch("collectors.unstop.safe_get", return_value=response(payload)), track_collector() as health:
        assert UnstopCollector().collect() == []
    assert health.issues
