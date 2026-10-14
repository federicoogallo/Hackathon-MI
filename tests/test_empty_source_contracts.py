from collectors.mlh import MLHCollector
from collectors.hackathon_com import HackathonComCollector
from utils.collector_health import track_collector
import pytest


def mlh_card(country="IT", city="Milano", mode="Offline", title="Aurora Hack"):
    return f'''<a itemscope itemtype="https://schema.org/Event" href="https://example.org/">
      <meta itemprop="url" content="https://example.org/">
      <meta itemprop="eventAttendanceMode" content="https://schema.org/{mode}EventAttendanceMode">
      <meta itemprop="startDate" content="2027-01-12T10:00:00Z">
      <meta itemprop="endDate" content="2027-01-13T18:00:00Z">
      <div itemprop="location" itemscope itemtype="https://schema.org/Place">
        <span itemprop="name">Wrong title</span>
        <meta itemprop="addressLocality" content="{city}">
        <meta itemprop="addressCountry" content="{country}">
      </div><h4>{title}</h4></a>'''


def test_mlh_reads_new_structured_cards_and_full_date_range():
    collector = MLHCollector()
    events = collector._parse_html(mlh_card(), set())
    assert len(events) == 1
    event = events[0]
    assert event.title == "Aurora Hack"
    assert event.location == "Milano, IT"
    assert event.date_str == "2027-01-12T10:00:00Z — 2027-01-13T18:00:00Z"
    assert event.date_source == "structured_data"


def test_mlh_excludes_online_and_false_geographic_names_without_parser_error():
    for markup in [mlh_card(country="US", city="Milan", title="Italian Hack"),
                   mlh_card(mode="Online"), mlh_card(mode="Online", country="")]:
        with track_collector() as health:
            assert MLHCollector()._parse_html(markup, set()) == []
        assert health.outcome(0) == "empty"


@pytest.mark.parametrize("markup", [
    '<main id="app"></main>',
    '<script id="__NEXT_DATA__">not json</script>',
    '<script id="__NEXT_DATA__">{"props":{"pageProps":{"error":true}}}</script>',
    '<div class="event-container"></div>',
    '<a itemscope itemtype="https://schema.org/Event"></a>',
])
def test_unrecognized_mlh_shell_is_not_a_successful_empty_listing(markup):
    with track_collector() as health:
        assert MLHCollector()._parse_html(markup, set()) == []
    assert health.issues[0]["kind"] == "parse_error"


def test_hackathon_com_explicit_empty_state_is_valid():
    with track_collector() as health:
        assert HackathonComCollector()._parse_html(
            '<main>There is no upcoming  hackathons found in "Milan, Italy"</main>', set()) == []
    assert health.outcome(0) == "empty"


def test_hackathon_com_changed_page_is_diagnosed():
    with track_collector() as health:
        assert HackathonComCollector()._parse_html('<main id="app"></main>', set()) == []
    assert health.issues[0]["kind"] == "parse_error"


def test_duplicate_hackathon_com_listing_is_not_a_parse_error():
    collector = HackathonComCollector()
    markup = '<article><a href="https://www.hackathon.com/hackathon/one"><h2>Aurora Hackathon</h2></a></article>'
    seen = set()
    with track_collector() as health:
        assert len(collector._parse_html(markup, seen)) == 1
        assert collector._parse_html(markup, seen) == []
    assert health.issues == []


def test_hackathon_com_current_cards_preserve_historical_evidence_without_guessing_year():
    html = '''<div class="ht-event-card">
        <a class="ht-event-card__banner" href="/event/example"></a>
        <a class="ht-event-card__title" href="/event/example">Aurora Hackathon</a>
        <div class="ht-event-card__date">22 Oct - 04:00 PM</div>
        <div class="ht-event-card__location">Roma, Italy</div>
        <div class="ht-event-card__desc">Evento del 2019.</div></div>'''
    with track_collector() as health:
        events = HackathonComCollector()._parse_html(html, set())
    assert len(events) == 1
    assert events[0].title == "Aurora Hackathon"
    assert events[0].url == "https://www.hackathon.com/event/example"
    assert events[0].date_str == ""
    assert "2019" in events[0].description
    assert events[0].location == "Roma, Italy"
    assert health.issues == []
