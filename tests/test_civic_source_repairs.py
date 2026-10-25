"""Source-specific records must survive markup changes without importing menus or dates as facts."""

from unittest.mock import patch

import pytest

from collectors.codemotion import CodemotionCollector
from collectors.comune_milano import ComuneMilanoCollector
from collectors.regione_lombardia import RegioneLombardiaCollector
from collectors.universities import UniversitiesCollector
from utils.collector_health import track_collector


@pytest.mark.parametrize(('domain', 'html', 'date', 'published'), [
    ('polimi.it', '''<nav class="card"><h5>Eventi</h5><a href="/eventi">Menu</a></nav>
    <div class="card card--editorial-photo"><a href="/il-politecnico/eventi/dettaglio-evento/aurora"><img></a>
    <h5 class="card-title">Aurora Hackathon</h5><div class="card-body__date"><p>30 <span>ottobre</span> <span>2026</span></p></div>
    <div class="card-text">Sfida per studenti</div></div>''', '2026-10-30', ''),
    ('iulm.it', '''<div class="rigaevento" data-date="30/10/2026" data-abstract="Sfida per studenti">
    <h4>Università</h4><h2><a href="/it/news-ed-eventi/news/aurora">Aurora Hackathon</a></h2></div>''', '30/10/2026', ''),
    ('unisr.it', '''<div class="newscard"><figure data-linkManager-href="/news/2026/10/aurora">
    <figcaption><span>Eventi</span><small>15 ottobre 2026</small><h2>Aurora Hackathon</h2></figcaption></figure></div>''', '', '15 ottobre 2026'),
])
def test_current_university_record_markup(domain, html, date, published):
    collector = UniversitiesCollector()
    with track_collector() as health:
        events = collector._extract_events(html, f'https://www.{domain}/', domain, 'University', set())
    assert not health.issues
    assert len(events) == 1
    event = events[0]
    assert event.title == 'Aurora Hackathon'
    assert event.date_str == date
    assert event.published_at == published
    assert event.location == ''


def test_university_rejects_foreign_links_and_unknown_markup():
    collector = UniversitiesCollector()
    with track_collector() as health:
        assert collector._extract_events('<div>Verify you are human</div>', 'https://www.iulm.it/', 'iulm.it', 'IULM', set()) == []
    assert health.issues[0]['kind'] == 'parse_error'
    html = '<div class="rigaevento" data-date="30/10/2026"><h2><a href="https://elsewhere.test/event">Aurora Hackathon</a></h2></div>'
    assert collector._extract_events(html, 'https://www.iulm.it/', 'iulm.it', 'IULM', set()) == []


def test_codemotion_card_preserves_evidence_without_guessing_year():
    html = '''<a href="/events">Browse events</a><a class="v-card" href="https://community.codemotion.com/group/meetups/aurora">
    <div class="event-type">hackathon</div><div class="event-calendar"><div>Oct</div><div>30</div></div>
    <div class="event-desc"><h2>Aurora Hackathon</h2></div><h6 class="event-organizer">Example Community</h6>
    <span class="event-topics"><span>Milano <span>•</span></span><span>Italian</span></span></a>'''
    events = CodemotionCollector()._parse_html(html, 'https://events.codemotion.com/', set())
    assert len(events) == 1
    assert events[0].location == 'Milano'
    assert events[0].organizer == 'Example Community'
    assert events[0].date_str == ''
    assert events[0].date_source == 'unknown'
    assert 'Oct 30' in events[0].description
    explicit = html.replace('<div>30</div>', '<div>30</div><div>2027</div>')
    assert CodemotionCollector()._parse_html(explicit, 'https://events.codemotion.com/', set())[0].date_str == 'Oct 30 2027'


@pytest.mark.parametrize('collector', [CodemotionCollector, RegioneLombardiaCollector, ComuneMilanoCollector])
def test_unknown_shell_is_reported_not_healthy_empty(collector):
    with track_collector() as health:
        assert collector()._parse_html('<html><h1>Please enable JavaScript</h1></html>', 'https://example.test/', set()) == []
    assert health.issues[0]['kind'] == 'parse_error'


def test_open_innovation_news_and_deadline_are_not_event_dates():
    html = '''<nav><a href="/news/news/all-news">Tutte le notizie</a></nav>
    <div class="card card-img"><a href="/it/news/news/9508/aurora"><h3 class="card-title">Aurora Hackathon</h3></a>
    <div class="card-calendar"><span>13</span><span>ott</span><span>2026</span></div><p class="card-description">Hackathon il 29 ottobre a Milano</p></div>
    <div class="icon-challenge"><div class="content-icon-challenge"><div class="title">Boreale Challenge</div></div>
    <div class="badge-deadline">20 ottobre 2026</div><a href="/it/open_challenge/open-challenge/150/boreale">Scopri</a></div>'''
    seen = set()
    collector = RegioneLombardiaCollector()
    events = collector._parse_html(html, 'https://www.openinnovation.regione.lombardia.it/', seen)
    assert len(events) == 2
    assert events[0].published_at == '13 ott 2026'
    assert events[0].date_str == events[1].date_str == ''
    assert events[1].date_source == 'deadline'
    assert 'Scadenza candidature: 20 ottobre 2026' in events[1].description
    assert collector._parse_html(html, 'https://www.openinnovation.regione.lombardia.it/', seen) == []


def test_municipal_news_excludes_service_links_and_preserves_publication_date():
    html = '''<div class="card"><h3><a href="/servizi/hackathon">Servizio Hackathon</a></h3></div>
    <article><h3><a href="/w/aurora">Aurora Hackathon</a></h3><time datetime="2026-10-13">13 ottobre</time><p>Il 29 ottobre a Milano</p></article>'''
    events = ComuneMilanoCollector()._parse_html(html, 'https://www.comune.milano.it/notizie', set())
    assert len(events) == 1
    assert events[0].published_at == '2026-10-13'
    assert events[0].date_str == ''
    assert events[0].location == ''


def test_repeated_civic_listings_do_not_look_like_parser_failures():
    from collectors.camera_commercio import CameraCommercioCollector
    html = '<article><h3><a href="/-/aurora">Aurora Hackathon</a></h3></article>'
    for collector, base in [(ComuneMilanoCollector(), 'https://www.comune.milano.it/'),
                            (CameraCommercioCollector(), 'https://www.milomb.camcom.it/')]:
        seen = set()
        with track_collector() as health:
            assert len(collector._parse_html(html, base, seen)) == 1
            assert collector._parse_html(html, base, seen) == []
        assert health.issues == []


def test_civic_collectors_use_current_hubs():
    seen = []
    def get(url, **kwargs):
        seen.append(url)
        return None
    for module, collector in [('universities', UniversitiesCollector), ('codemotion', CodemotionCollector), ('regione_lombardia', RegioneLombardiaCollector), ('comune_milano', ComuneMilanoCollector)]:
        with patch(f'collectors.{module}.safe_get', side_effect=get):
            collector().collect()
    assert 'https://www.polimi.it/il-politecnico/eventi' in seen
    assert 'https://www.iulm.it/it/news-ed-eventi/eventi' in seen
    assert 'https://www.unisr.it/news?category=eventi' in seen
    assert 'https://events.codemotion.com/' in seen
    assert 'https://www.comune.milano.it/notizie' in seen
    assert 'https://www.polimi.it/en/news-and-events' not in seen
    assert 'https://www.comune.milano.it/servizi/partecipa' not in seen


def test_polihub_does_not_turn_calendar_links_or_unrecognized_shell_into_events():
    from collectors.polihub import PoliHubCollector
    html = '<nav><a href="https://polihub.it/category/eventi/">Tutti gli eventi</a></nav>'
    with track_collector() as health:
        assert PoliHubCollector()._parse_html(html, 'https://polihub.it/', set()) == []
    assert health.issues[0]['kind'] == 'parse_error'
    html = '''<article><h3><a href="/eventi">Tutti gli eventi</a></h3></article>
    <article><h3><a href="/news/aurora">Aurora Hackathon</a></h3><time datetime="2026-10-14">14 ottobre</time><p>Nuovo evento</p></article>'''
    events = PoliHubCollector()._parse_html(html, 'https://polihub.it/category/eventi/', set())
    assert len(events) == 1
    assert events[0].published_at == '2026-10-14'
    assert events[0].date_str == ''
    assert events[0].location == ''


def test_current_comune_cards_include_legacy_liferay_paths_and_editorial_dates():
    html = '''<div class="card card-comunicato card-img"><div class="card-body">
    <div class="category-top"><span class="category">Comunicati Stampa</span><span class="data">14/10/2026</span></div>
    <h3 class="card-title"><a href="/-/aurora-hackathon">Aurora Hackathon</a></h3>
    <div class="card-text"><p>Il 29 ottobre la sfida a Milano</p></div></div></div>'''
    event = ComuneMilanoCollector()._parse_html(html, 'https://www.comune.milano.it/notizie', set())[0]
    assert event.url == 'https://www.comune.milano.it/-/aurora-hackathon'
    assert event.published_at == '14/10/2026'
    assert event.date_str == ''
    assert '29 ottobre' in event.description


def test_camera_does_not_count_imperva_http_200_challenge_as_empty_catalogue():
    from collectors.camera_commercio import CameraCommercioCollector
    html = '<html><head><meta name="robots" content="noindex,nofollow"><script src="/_Incapsula_Resource?SWJIYLWA=example"></script></head><body></body></html>'
    with track_collector() as health:
        assert CameraCommercioCollector()._parse_html(html, 'https://www.milomb.camcom.it/eventi', set()) == []
    assert health.issues[0]['kind'] == 'blocked'
    with track_collector() as health:
        assert CameraCommercioCollector()._parse_html('<html>New layout</html>', 'https://www.milomb.camcom.it/eventi', set()) == []
    assert health.issues[0]['kind'] == 'parse_error'


def _polimi_card(date_markup):
    return f'''<div class="card card--editorial-photo"><a href="/il-politecnico/eventi/dettaglio-evento/aurora"><img></a>
    <h5 class="card-title">Aurora Hackathon</h5>
    <div class="card-body__item card-body__date">
    <!-- Alert: dat inizio evento > data fine -->
    {date_markup}
    </div><div class="card-text">Sfida per studenti</div></div>'''


# Markup as served by polimi.it on 2026-10-25, tabs and template comments included.
@pytest.mark.parametrize(('date_markup', 'expected'), [
    ('<!-- Stessa data -->\n<p>\n\t\t\t26\n\t\t\t<span class="month">ottobre</span>\n<span class="year">2026</span>\n</p>',
     '2026-10-26'),
    ('<!-- Stesso mese e anno -->\n<p>\n\t\t\t04 – 11\n\t\t\t<span class="month">novembre</span>\n<span class="year">2026</span>\n</p>',
     '2026-11-04 — 2026-11-11'),
    ('<!-- Stesso anno, mesi diversi -->\n<p>\n\t\t\t20\n\t\t\t<span class="month">ottobre</span>\n\t\t\t→\n\t\t\t18\n'
     '\t\t\t<span class="month">dicembre</span>\n<span class="year">2026</span>\n</p>',
     '2026-10-20 — 2026-12-18'),
    ('<p>28 <span class="month">dicembre</span> <span class="year">2026</span> → 06 '
     '<span class="month">gennaio</span> <span class="year">2027</span></p>',
     '2026-12-28 — 2027-01-06'),
    # Shapes the card is not known to use stay as printed, for review.
    ('<p>18 <span class="month">dicembre</span> → 20 <span class="month">ottobre</span> '
     '<span class="year">2026</span></p>', '18 dicembre → 20 ottobre 2026'),
    ('<p>\n\t\tDa definire\n</p>', 'Da definire'),
])
def test_polimi_card_dates_become_iso_dates(date_markup, expected):
    events = UniversitiesCollector()._extract_events(
        _polimi_card(date_markup), 'https://www.polimi.it/il-politecnico/eventi', 'polimi.it', 'Politecnico di Milano', set())
    assert [event.date_str for event in events] == [expected]
    assert events[0].date_source == 'event_card'
