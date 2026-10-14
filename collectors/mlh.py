"""Major League Hacking season listings, including structured Event cards."""

import logging
from datetime import datetime
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from models import BaseCollector, HackathonEvent
from utils.collector_health import record_issue
from utils.http import safe_get

logger = logging.getLogger(__name__)

# MLH pubblica le stagioni con anno accademico
CURRENT_YEAR = datetime.now().year
MLH_URLS = [
    f"https://www.mlh.com/seasons/{CURRENT_YEAR}/events",
    f"https://www.mlh.com/seasons/{CURRENT_YEAR + 1}/events",
]


class MLHCollector(BaseCollector):

    @property
    def name(self) -> str:
        return "mlh"

    def collect(self) -> list[HackathonEvent]:
        all_events: list[HackathonEvent] = []
        seen_urls: set[str] = set()

        for url in MLH_URLS:
            events = self._fetch_season(url, seen_urls)
            all_events.extend(events)

        logger.info("MLH: trovati %d eventi (Italia/Milano)", len(all_events))
        return all_events

    def _fetch_season(self, url: str, seen_urls: set[str]) -> list[HackathonEvent]:
        """Fetch una stagione MLH e filtra per Italia."""
        response = safe_get(url)
        if response is None:
            return []

        return self._parse_html(response.text, seen_urls)

    def _parse_html(self, html: str, seen_urls: set[str]) -> list[HackathonEvent]:
        """Parsa la pagina eventi MLH."""
        soup = BeautifulSoup(html, "lxml")
        events: list[HackathonEvent] = []

        structured = soup.select('[itemscope][itemtype="https://schema.org/Event"]')
        if structured:
            for card in structured:
                event = self._parse_structured_card(card, seen_urls)
                if event:
                    events.append(event)
            return events

        if "no events" not in soup.get_text(" ", strip=True).lower():
            record_issue("parse_error", "MLH structured event listing not recognized")
        return events

    def _parse_structured_card(self, card, seen_urls: set[str]) -> HackathonEvent | None:
        def value(prop: str, root=None) -> str:
            element = (root if root is not None else card).select_one(f'[itemprop="{prop}"]')
            return (element.get("content") or element.get_text(" ", strip=True)) if element else ""

        location = card.select_one('[itemprop="location"]')
        country = value("addressCountry", location) if location else ""
        if value("eventAttendanceMode").endswith("OnlineEventAttendanceMode"):
            return None
        # Location.name precedes Event.name in the markup; select the event heading explicitly.
        title_el = card.select_one("h2, h3, h4")
        title = title_el.get_text(" ", strip=True) if title_el else ""
        url = value("url")
        try:
            parts = urlsplit(url)
            valid_url = parts.scheme in {"https", "http"} and parts.hostname and not parts.username
        except ValueError:
            valid_url = False
        if not title or not valid_url or not country:
            record_issue("parse_error", "MLH event card missing title, URL or country")
            return None
        if country.lower() not in {"it", "italy", "italia"}:
            return None
        if url in seen_urls:
            return None
        seen_urls.add(url)
        start, end = value("startDate"), value("endDate")
        return HackathonEvent(
            title=title, url=url, source=self.name,
            date_str=f"{start} — {end}" if start and end and start != end else start,
            date_source="structured_data" if start else "unknown",
            location=", ".join(filter(None, [value("addressLocality", location),
                                            value("addressRegion", location), country])),
            organizer="Major League Hacking",
        )
