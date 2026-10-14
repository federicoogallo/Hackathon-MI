"""Collect public news and challenges from Regione Lombardia's Open Innovation portal."""

import logging
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from models import BaseCollector, HackathonEvent
from utils.collector_health import record_issue
from utils.http import safe_get

logger = logging.getLogger(__name__)

REGIONE_URLS = [
    "https://www.openinnovation.regione.lombardia.it/news/news/all-news",
    "https://www.openinnovation.regione.lombardia.it/it/iniziative/open-challenge/le-sfide",
]


class RegioneLombardiaCollector(BaseCollector):
    @property
    def name(self) -> str:
        return "regione_lombardia"

    def collect(self) -> list[HackathonEvent]:
        events: list[HackathonEvent] = []
        seen: set[str] = set()
        for url in REGIONE_URLS:
            response = safe_get(url)
            if response is not None:
                events.extend(self._parse_html(response.text, url, seen))
        logger.info("Regione Lombardia: trovati %d eventi", len(events))
        return events

    def _parse_html(self, html: str, base_url: str, seen_urls: set[str]) -> list[HackathonEvent]:
        soup = BeautifulSoup(html, "lxml")
        cards = soup.select(".card.card-img, .icon-challenge")
        if not cards:
            text = soup.get_text(" ", strip=True).lower()
            if not any(marker in text for marker in ("nessun risultato", "nessun elemento", "nessuna sfida")):
                record_issue("parse_error", "Open Innovation listing not recognized", base_url)
            return []
        events = []
        for card in cards:
            challenge = "icon-challenge" in card.get("class", [])
            if challenge:
                title_el = card.select_one(".content-icon-challenge .title")
                link = card.select_one('a[href*="/open_challenge/open-challenge/"]')
                date_el = card.select_one(".badge-deadline")
                desc_el = None
            else:
                title_el = card.select_one(".card-title")
                link = title_el.find_parent("a", href=True) if title_el else None
                date_el = card.select_one(".card-calendar")
                desc_el = card.select_one(".card-description")
            if title_el is None or link is None:
                continue
            title = title_el.get_text(" ", strip=True)
            url = urljoin(base_url, link["href"])
            parts = urlparse(url)
            if (len(title) < 5 or url in seen_urls or parts.scheme not in {"http", "https"}
                    or parts.hostname not in {"www.openinnovation.regione.lombardia.it", "openinnovation.regione.lombardia.it"}
                    or not re.search(r"/(?:news/news|open_challenge/open-challenge)/\d+/", parts.path)):
                continue
            date = date_el.get_text(" ", strip=True) if date_el else ""
            description = desc_el.get_text(" ", strip=True) if desc_el else ""
            # Neither an application deadline nor a publication date is the event date.
            if challenge and date:
                description = f"Scadenza candidature: {date}. {description}".strip()
            seen_urls.add(url)
            events.append(HackathonEvent(
                title=title, url=url, source=self.name, description=description[:500],
                date_str="", published_at="" if challenge else date,
                date_source="deadline" if challenge else "publication",
                location="", organizer="Regione Lombardia",
            ))
        return events
