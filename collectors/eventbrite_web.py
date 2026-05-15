"""
Collector Eventbrite (HTML scraping, nessuna API key).

Strategia: fetch della pagina categoria hackathon Milano e parsing del JSON-LD
(<script type="application/ld+json">) che Eventbrite include server-side.
Funziona anche in GitHub Actions (non usa DuckDuckGo/DDGS).
"""

import json
import logging

from bs4 import BeautifulSoup

import config
from models import BaseCollector, HackathonEvent
from utils.http import safe_get

logger = logging.getLogger(__name__)

# Pagine Eventbrite con ricerca hackathon/tech Milano — nessuna API key richiesta
EVENTBRITE_URLS = [
    "https://www.eventbrite.com/d/italy--milan/hackathon/",
    "https://www.eventbrite.com/d/italy--milan/technology/",
]


class EventbriteWebCollector(BaseCollector):
    """Scraper HTML di Eventbrite senza API key, basato su JSON-LD."""

    @property
    def name(self) -> str:
        return "eventbrite_web"

    def collect(self) -> list[HackathonEvent]:
        events: list[HackathonEvent] = []
        seen_urls: set[str] = set()

        for url in EVENTBRITE_URLS:
            page_events = self._fetch_page(url)
            for ev in page_events:
                if ev.url not in seen_urls:
                    seen_urls.add(ev.url)
                    events.append(ev)

        logger.info("EventbriteWeb: trovati %d eventi (dedup) su %d URL", len(events), len(EVENTBRITE_URLS))
        return events

    def _fetch_page(self, url: str) -> list[HackathonEvent]:
        response = safe_get(url, timeout=15)
        if response is None:
            logger.warning("EventbriteWeb: impossibile raggiungere %s", url)
            return []

        if response.status_code != 200:
            logger.warning("EventbriteWeb: HTTP %d per %s", response.status_code, url)
            return []

        soup = BeautifulSoup(response.text, "lxml")

        # Il JSON-LD migliore è il primo script — contiene itemListElement con tutti gli eventi
        ld_scripts = soup.find_all("script", type="application/ld+json")
        for script in ld_scripts:
            if not script.string:
                continue
            try:
                data = json.loads(script.string)
            except json.JSONDecodeError:
                continue

            items = data.get("itemListElement", [])
            if not items:
                continue

            events = []
            for item_wrap in items:
                ev = self._parse_item(item_wrap)
                if ev:
                    events.append(ev)

            if events:
                logger.debug("EventbriteWeb: %d eventi da JSON-LD su %s", len(events), url)
                return events

        logger.warning("EventbriteWeb: nessun JSON-LD con itemListElement trovato su %s", url)
        return []

    def _parse_item(self, item_wrap: dict) -> HackathonEvent | None:
        """Converte un item del JSON-LD Eventbrite in HackathonEvent."""
        try:
            item = item_wrap.get("item", item_wrap)
            if item.get("@type") != "Event":
                return None

            title = (item.get("name", "") or "").strip()
            if not title:
                return None

            url = item.get("url", "") or ""
            # Normalizza URL: usa eventbrite.it per eventi italiani
            if not url:
                return None

            description = (item.get("description", "") or "")[:500]

            # Date
            start_date = item.get("startDate", "") or ""
            end_date = item.get("endDate", "") or ""
            if end_date and end_date != start_date:
                date_str = f"{start_date} — {end_date}"
            else:
                date_str = start_date

            # Location
            location = ""
            loc = item.get("location", {}) or {}
            if isinstance(loc, dict):
                addr = loc.get("address", {}) or {}
                if isinstance(addr, dict):
                    city = addr.get("addressLocality", "")
                    street = addr.get("streetAddress", "")
                    if city:
                        location = f"{street}, {city}".strip(", ") if street else city

            return HackathonEvent(
                title=title,
                url=url,
                source=self.name,
                description=description,
                date_str=date_str,
                location=location,
            )

        except Exception as exc:
            logger.debug("EventbriteWeb: errore parsing item: %s", exc)
            return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    collector = EventbriteWebCollector()
    events = collector.collect()
    print(f"Totale eventi: {len(events)}")
    for e in events[:10]:
        print(f"  [{e.date_str or 'n/d'}] {e.title}")
        print(f"    {e.url[:80]}")
