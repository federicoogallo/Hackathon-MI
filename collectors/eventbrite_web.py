"""
Collector Eventbrite (HTML scraping, nessuna API key).

Strategia: fetch della pagina categoria hackathon Milano e parsing del JSON-LD
(<script type="application/ld+json">) che Eventbrite include server-side.
Non richiede chiavi API. I blocchi HTTP vengono riportati nella salute della fonte.
"""

import json
import logging

from bs4 import BeautifulSoup

from models import BaseCollector, HackathonEvent
from utils.http import safe_get
from utils.collector_health import record_issue

logger = logging.getLogger(__name__)

# Pagine Eventbrite con ricerca hackathon/tech Milano — nessuna API key richiesta
EVENTBRITE_URLS = [
    "https://www.eventbrite.com/d/italy--milano/hackathon/",
    "https://www.eventbrite.com/d/italy--milano/technology/",
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

        events = []
        recognised = False
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                payload = json.loads(script.get_text())
            except (ValueError, TypeError):
                continue
            nodes = list(payload) if isinstance(payload, list) else [payload]
            while nodes:
                node = nodes.pop(0)
                if not isinstance(node, dict):
                    continue
                if isinstance(node.get("@graph"), list):
                    nodes.extend(node["@graph"])
                # BreadcrumbList also has itemListElement, but is not an event list.
                if node.get("@type") == "ItemList" and isinstance(node.get("itemListElement"), list):
                    items = node["itemListElement"]
                    list_events = []
                    for item in items:
                        event = self._parse_item(item)
                        if event:
                            list_events.append(event)
                    if items and not list_events:
                        record_issue("parse_error", "nonempty ItemList has no readable events", url)
                    else:
                        recognised = True
                    events.extend(list_events)
        if not recognised:
            record_issue("parse_error", "event ItemList missing", url)
        return events

    def _parse_item(self, item_wrap: dict) -> HackathonEvent | None:
        """Converte un item del JSON-LD Eventbrite in HackathonEvent."""
        try:
            if not isinstance(item_wrap, dict):
                return None
            item = item_wrap.get("item", item_wrap)
            if not isinstance(item, dict) or item.get("@type") != "Event":
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
            start_date = item.get("startDate") if isinstance(item.get("startDate"), str) else ""
            end_date = item.get("endDate") if isinstance(item.get("endDate"), str) else ""
            start_date, end_date = start_date.strip(), end_date.strip()
            if start_date and end_date and end_date != start_date:
                date_str = f"{start_date} — {end_date}"
            else:
                date_str = start_date
            if end_date and not start_date:
                description = f"{description} Fine evento indicata dalla fonte: {end_date}.".strip()

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
                date_source="event_jsonld" if start_date else "",
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
