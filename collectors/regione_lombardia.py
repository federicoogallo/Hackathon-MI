"""
Collector Regione Lombardia — scraping Open Innovation portal.

Recupera hackathon finanziati regionalmente e challenge d'innovazione.
URL: https://www.openinnovation.regione.lombardia.it
"""

import logging

from bs4 import BeautifulSoup

import config
from models import BaseCollector, HackathonEvent
from utils.http import safe_get

logger = logging.getLogger(__name__)

REGIONE_URLS = [
    "https://www.openinnovation.regione.lombardia.it/it/opportunita",
    "https://www.openinnovation.regione.lombardia.it/it/eventi",
    "https://www.regione.lombardia.it/wps/portal/istituzionale/HP/bandi",
]


class RegioneLombardiaCollector(BaseCollector):

    @property
    def name(self) -> str:
        return "regione_lombardia"

    def collect(self) -> list[HackathonEvent]:
        all_events: list[HackathonEvent] = []
        seen_urls: set[str] = set()

        for url in REGIONE_URLS:
            response = safe_get(url)
            if response is None:
                continue
            events = self._parse_html(response.text, url, seen_urls)
            all_events.extend(events)

        logger.info("Regione Lombardia: trovati %d eventi", len(all_events))
        return all_events

    def _parse_html(self, html: str, base_url: str, seen_urls: set[str]) -> list[HackathonEvent]:
        """Parsa le pagine della Regione Lombardia."""
        soup = BeautifulSoup(html, "lxml")
        events: list[HackathonEvent] = []

        cards = soup.find_all("article")
        if not cards:
            cards = soup.find_all("div", class_=lambda c: c and ("card" in str(c).lower() or "item" in str(c).lower() or "event" in str(c).lower() or "opportunity" in str(c).lower()))
        if not cards:
            cards = soup.find_all("li", class_=lambda c: c and ("item" in str(c).lower() or "result" in str(c).lower()))

        for card in cards:
            link = card.find("a", href=True)
            if not link:
                continue

            url = link.get("href", "").strip()
            title_el = card.find(["h2", "h3", "h4"])
            title = title_el.get_text(strip=True) if title_el else link.get_text(strip=True)

            if not url or not title or len(title) < 5 or url in seen_urls:
                continue
            if not url.startswith("http"):
                from urllib.parse import urljoin
                url = urljoin(base_url, url)
            seen_urls.add(url)

            date_el = card.find(["time"]) or card.find(class_=lambda c: c and "date" in str(c).lower())
            date_str = ""
            if date_el:
                date_str = date_el.get("datetime", "") or date_el.get_text(strip=True)

            desc_el = card.find(class_=lambda c: c and ("desc" in str(c).lower() or "text" in str(c).lower() or "abstract" in str(c).lower()))
            description = desc_el.get_text(strip=True)[:500] if desc_el else ""

            events.append(HackathonEvent(
                title=title,
                url=url,
                source=self.name,
                description=description,
                date_str=date_str,
                location="Lombardia",
                organizer="Regione Lombardia",
            ))

        return events
