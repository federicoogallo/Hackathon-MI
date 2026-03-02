"""
Collector Eventbrite — usa l'API REST ufficiale.

Cerca hackathon a Milano con multiple keyword per massimizzare la copertura.
Gestisce paginazione e normalizza i risultati in HackathonEvent.
"""

import logging

import config
from models import BaseCollector, HackathonEvent
from utils.http import safe_get_json

logger = logging.getLogger(__name__)

API_BASE = "https://www.eventbriteapi.com/v3"

# Keyword di ricerca (una query API per ciascuna)
SEARCH_QUERIES = [
    "hackathon",
    "coding challenge",
    "codathon",
    "buildathon",
    "code jam",
]

MAX_PAGES = 3  # Pagine per query (50 risultati/pagina)


class EventbriteCollector(BaseCollector):

    @property
    def name(self) -> str:
        return "eventbrite"

    def collect(self) -> list[HackathonEvent]:
        if not config.EVENTBRITE_API_KEY:
            logger.warning("EVENTBRITE_API_KEY non configurata — skip collector")
            return []

        headers = {"Authorization": f"Bearer {config.EVENTBRITE_API_KEY}"}
        all_events: list[HackathonEvent] = []
        seen_ids: set[str] = set()  # Dedup interna tra query diverse

        for query in SEARCH_QUERIES:
            events = self._search(query, headers, seen_ids)
            all_events.extend(events)

        logger.info("Eventbrite: trovati %d eventi totali", len(all_events))
        return all_events

    def _search(
        self, query: str, headers: dict, seen_ids: set[str]
    ) -> list[HackathonEvent]:
        """Cerca una keyword specifica con paginazione."""
        events: list[HackathonEvent] = []

        for page in range(1, MAX_PAGES + 1):
            params = {
                "q": query,
                "location.address": f"{config.SEARCH_LOCATION}, {config.SEARCH_COUNTRY}",
                "location.within": f"{config.SEARCH_RADIUS_KM}km",
                "expand": "venue,organizer",
                "page": page,
            }

            data = safe_get_json(
                f"{API_BASE}/events/search/",
                params=params,
                headers=headers,
            )

            if not data or not isinstance(data, dict):
                break

            raw_events = data.get("events", [])
            if not raw_events:
                break

            for raw in raw_events:
                event = self._parse_event(raw)
                if event and event.id not in seen_ids:
                    seen_ids.add(event.id)
                    events.append(event)

            # Controlla se ci sono altre pagine
            pagination = data.get("pagination", {})
            if page >= pagination.get("page_count", 1):
                break

        return events

    def _parse_event(self, raw: dict) -> HackathonEvent | None:
        """Converte un evento Eventbrite raw in HackathonEvent."""
        try:
            title = raw.get("name", {}).get("text", "").strip()
            url = raw.get("url", "").strip()

            if not title or not url:
                return None

            description = raw.get("description", {}).get("text", "") or ""
            description = description[:1000]  # Tronca descrizioni enormi

            # Date
            start = raw.get("start", {})
            end = raw.get("end", {})
            date_str = start.get("local", "")
            if end.get("local"):
                date_str += f" — {end['local']}"

            # Location
            venue = raw.get("venue", {})
            if venue:
                addr = venue.get("address", {})
                location = addr.get("localized_address_display", config.SEARCH_LOCATION)
            else:
                location = config.SEARCH_LOCATION

            # Organizer
            organizer_data = raw.get("organizer", {})
            organizer = organizer_data.get("name", "") if organizer_data else ""

            return HackathonEvent(
                title=title,
                url=url,
                source=self.name,
                description=description,
                date_str=date_str,
                location=location,
                organizer=organizer,
            )

        except Exception as e:
            logger.warning("Errore parsing evento Eventbrite: %s", e)
            return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    collector = EventbriteCollector()
    events = collector.collect()
    for e in events:
        print(f"  [{e.source}] {e.title} — {e.url}")
