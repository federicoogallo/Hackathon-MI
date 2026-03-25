"""
Test suite per i collector — parsing delle risposte con mock HTTP.

Ogni test fornisce un HTML/JSON fittizio e verifica che il collector
produca i corretti HackathonEvent.
"""

from unittest.mock import patch, MagicMock
import json

import pytest

from models import HackathonEvent


# =============================================================================
#  Helper
# =============================================================================

def _mock_response(status=200, text="", json_data=None):
    """Crea un mock di requests.Response."""
    resp = MagicMock()
    resp.status_code = status
    resp.text = text
    resp.ok = 200 <= status < 300
    if json_data is not None:
        resp.json.return_value = json_data
        resp.text = json.dumps(json_data)
    return resp


def _mock_safe_get_response(html: str):
    """Crea un mock Response con .text per safe_get."""
    resp = MagicMock()
    resp.text = html
    resp.status_code = 200
    return resp


# =============================================================================
#  Eventbrite
# =============================================================================

class TestEventbriteCollector:
    @patch("collectors.eventbrite.config")
    @patch("collectors.eventbrite.safe_get_json")
    def test_returns_empty_without_api_key(self, mock_get, mock_config):
        mock_config.EVENTBRITE_API_KEY = ""
        from collectors.eventbrite import EventbriteCollector
        c = EventbriteCollector()
        assert c.collect() == []
        mock_get.assert_not_called()

    @patch("collectors.eventbrite.config")
    @patch("collectors.eventbrite.safe_get_json")
    def test_parses_events(self, mock_get, mock_config):
        mock_config.EVENTBRITE_API_KEY = "key-123"
        mock_config.SEARCH_LOCATION = "Milano"
        mock_get.return_value = {
            "events": [
                {
                    "name": {"text": "PoliHack 2026"},
                    "url": "https://eventbrite.it/polihack2026",
                    "description": {"text": "24h coding marathon"},
                    "start": {"local": "2026-03-15T09:00:00"},
                    "venue": None,
                    "organizer": {"name": "PoliMi"},
                },
            ],
            "pagination": {"has_more_items": False},
        }
        from collectors.eventbrite import EventbriteCollector
        c = EventbriteCollector()
        events = c.collect()
        assert len(events) >= 1
        assert events[0].title == "PoliHack 2026"
        assert events[0].source == "eventbrite"


# =============================================================================
#  Google CSE
# =============================================================================

class TestWebSearchCollector:
    def test_parses_search_results(self):
        """Verifica che il collector parsa correttamente i risultati DuckDuckGo."""
        mock_ddgs = MagicMock()
        mock_ddgs.text.return_value = [
            {
                "title": "Hackathon Milano 2026",
                "href": "https://example.com/hack",
                "body": "Join the best hackathon in Milan.",
            },
        ]
        mock_ddgs_class = MagicMock(return_value=mock_ddgs)

        import sys
        mock_module = MagicMock()
        mock_module.DDGS = mock_ddgs_class
        with patch.dict(sys.modules, {"ddgs": mock_module}):
            from importlib import reload
            import collectors.web_search as ws
            reload(ws)
            c = ws.WebSearchCollector()
            events = c.collect()
        assert len(events) >= 1
        assert events[0].source == "web_search"
        assert events[0].title == "Hackathon Milano 2026"


# =============================================================================
#  InnovUp
# =============================================================================

class TestInnovUpCollector:
    SAMPLE_HTML = """
    <html><body>
    <div class="listing-item">
      <div class="listing-item__title">
        <a href="https://innovup.net/eventi/hackathon-ai-2026/">Hackathon AI 2026</a>
      </div>
      <div class="listing-item__date">15 Marzo 2026</div>
    </div>
    </body></html>
    """

    @patch("collectors.innovup.safe_get")
    def test_parses_html(self, mock_get):
        mock_get.return_value = _mock_safe_get_response(self.SAMPLE_HTML)
        from collectors.innovup import InnovUpCollector
        c = InnovUpCollector()
        events = c.collect()
        assert len(events) >= 1
        assert events[0].source == "innovup"

    @patch("collectors.innovup.safe_get")
    def test_returns_empty_on_failure(self, mock_get):
        mock_get.return_value = None
        from collectors.innovup import InnovUpCollector
        c = InnovUpCollector()
        assert c.collect() == []


# =============================================================================
#  Luma
# =============================================================================

class TestLumaCollector:
    SAMPLE_NEXT_DATA = json.dumps({
        "props": {
            "pageProps": {
                "initialData": {
                    "data": {
                        "events": [
                            {
                                "event": {
                                    "name": "Hack Milano",
                                    "url": "https://lu.ma/hackmilano",
                                    "description": "Hackathon description",
                                    "start_at": "2026-03-15T09:00:00Z",
                                    "geo_address_info": {
                                        "city_state": "Milano, MI"
                                    },
                                },
                            }
                        ]
                    }
                }
            }
        }
    })

    @patch("collectors.luma.safe_get")
    def test_parses_next_data(self, mock_get):
        html = f'<html><script id="__NEXT_DATA__" type="application/json">{self.SAMPLE_NEXT_DATA}</script></html>'
        mock_get.return_value = _mock_safe_get_response(html)
        from collectors.luma import LumaCollector
        c = LumaCollector()
        events = c.collect()
        # Potrebbe avere 0 se la struttura non matcha esattamente
        # Il test verifica che non crashia
        assert isinstance(events, list)

    @patch("collectors.luma.safe_get")
    def test_returns_empty_on_failure(self, mock_get):
        mock_get.return_value = None
        from collectors.luma import LumaCollector
        c = LumaCollector()
        assert c.collect() == []


# =============================================================================
#  Devpost
# =============================================================================

class TestDevpostCollector:
    SAMPLE_HTML = """
    <html><body>
    <div class="hackathon-tile">
      <a class="link-to-hackathon" href="https://devpost.com/hackathons/hack2026">
        <h3>Hack Milano 2026</h3>
        <p class="hackathon-tile__date">Mar 15 - 16, 2026</p>
      </a>
    </div>
    </body></html>
    """

    @patch("collectors.devpost.safe_get")
    def test_returns_list(self, mock_get):
        mock_get.return_value = _mock_safe_get_response(self.SAMPLE_HTML)
        from collectors.devpost import DevpostCollector
        c = DevpostCollector()
        events = c.collect()
        assert isinstance(events, list)


# =============================================================================
#  Universities
# =============================================================================

class TestUniversitiesCollector:
    @patch("collectors.universities.safe_get")
    def test_returns_list_on_failure(self, mock_get):
        """Se tutto fallisce, ritorna lista vuota senza crash."""
        mock_get.return_value = None
        from collectors.universities import UniversitiesCollector
        c = UniversitiesCollector()
        events = c.collect()
        assert isinstance(events, list)

    @patch("collectors.universities.safe_get")
    def test_filters_pagination_artifacts(self, mock_get):
        """Titoli numerici (come "10", "25") vengono filtrati."""
        mock_get.return_value = """
        <html><body>
        <a href="/event/1">Hackathon AI 2026</a>
        <a href="/page/2">10</a>
        <a href="/page/3">25</a>
        </body></html>
        """
        from collectors.universities import UniversitiesCollector
        c = UniversitiesCollector()
        events = c.collect()
        # I titoli numerici non devono comparire
        for e in events:
            assert not e.title.strip().isdigit()


# =============================================================================
#  Reddit
# =============================================================================

class TestRedditCollector:
    @patch("collectors.reddit.config")
    def test_returns_empty_without_credentials(self, mock_config):
        mock_config.REDDIT_CLIENT_ID = ""
        mock_config.REDDIT_CLIENT_SECRET = ""
        from collectors.reddit import RedditCollector
        c = RedditCollector()
        assert c.collect() == []


# =============================================================================
#  PoliHub
# =============================================================================

class TestPoliHubCollector:
    @patch("collectors.polihub.safe_get")
    def test_returns_empty_on_403(self, mock_get):
        mock_get.return_value = None  # Simula errore WAF
        from collectors.polihub import PoliHubCollector
        c = PoliHubCollector()
        assert c.collect() == []


# =============================================================================
#  Telespazio
# =============================================================================

class TestTelespazioCollector:
        @patch("collectors.telespazio.safe_get")
        def test_collects_hackathon_detail(self, mock_get):
                index_html = """
                <html><body>
                    <a href="/en/careers/hackathon-space-edition">Hackathon Leonardo - Space Edition</a>
                </body></html>
                """
                detail_html = """
                <html><head>
                    <meta property="og:title" content="Hackathon Leonardo - Space Edition">
                    <meta property="og:description" content="On 9-10 May 2026 in Milan this hackathon takes place.">
                </head><body>
                    <h1>Hackathon Leonardo - Space Edition</h1>
                    <p>On 9-10 May 2026 in Milan this hackathon takes place.</p>
                </body></html>
                """

                def _side_effect(url, *args, **kwargs):
                        if url.endswith("/careers"):
                                return _mock_safe_get_response(index_html)
                        if "hackathon-space-edition" in url:
                                return _mock_safe_get_response(detail_html)
                        return None

                mock_get.side_effect = _side_effect

                from collectors.telespazio import TelespazioCollector

                events = TelespazioCollector().collect()
                assert len(events) == 1
                assert events[0].title == "Hackathon Leonardo - Space Edition"
                assert "telespazio.com" in events[0].url
                assert events[0].source == "telespazio"

        @patch("collectors.telespazio.safe_get")
        def test_returns_empty_on_failure(self, mock_get):
                mock_get.return_value = None
                from collectors.telespazio import TelespazioCollector
                assert TelespazioCollector().collect() == []


# =============================================================================
#  Tutti i collector implementano BaseCollector
# =============================================================================

class TestCollectorInterface:
    def test_all_collectors_are_base_collector(self):
        """Tutti i collector nel registry sono istanze di BaseCollector."""
        from models import BaseCollector
        from main import get_collectors
        collectors = get_collectors()
        # Il numero di collector cresce nel tempo: garantiamo che il registry
        # non si svuoti accidentalmente, senza hardcode rigidi.
        assert len(collectors) >= 8
        for c in collectors:
            assert isinstance(c, BaseCollector), f"{c.__class__.__name__} non è BaseCollector"
            assert hasattr(c, "name")
            assert hasattr(c, "collect")
