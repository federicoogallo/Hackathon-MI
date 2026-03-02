"""
Collector Google Custom Search Engine — meta-aggregatore.

Cerca "hackathon Milano" su un motore di ricerca personalizzato
configurato con 17 siti specifici: Eventbrite, LinkedIn Events,
Meetup, Luma, Devpost, X/Twitter, università milanesi, ecc.

Usa ~6 query per run, ben dentro il limite gratuito di 100/giorno.

NOTA (gen 2026): Google ha rimosso "Search the entire web" per i nuovi CSE.
      Il motore è configurato con siti specifici, il che riduce il rumore.
"""

import logging
from datetime import datetime

import config
from models import BaseCollector, HackathonEvent
from utils.http import safe_get_json

logger = logging.getLogger(__name__)

CSE_API_URL = "https://www.googleapis.com/customsearch/v1"

# Query di ricerca — ogni query costa 1 "uso" (100 gratis/giorno)
# Non serve site: perché il CSE è già limitato ai siti configurati
SEARCH_QUERIES = [
    "hackathon Milano 2026",
    "hackathon Milan Italy",
    "coding challenge Milano",
    "hackathon Politecnico Milano OR Bocconi",
    "appathon OR codathon OR buildathon Milano",
    "hackathon startup innovation Milano",
]


class GoogleCSECollector(BaseCollector):

    @property
    def name(self) -> str:
        return "google_cse"

    def collect(self) -> list[HackathonEvent]:
        if not config.GOOGLE_CSE_API_KEY or not config.GOOGLE_CSE_CX:
            logger.warning("Google CSE non configurato (manca API_KEY o CX) — skip")
            return []

        all_events: list[HackathonEvent] = []
        seen_urls: set[str] = set()

        for query in SEARCH_QUERIES:
            events = self._search(query, seen_urls)
            all_events.extend(events)

        logger.info("Google CSE: trovati %d risultati totali", len(all_events))
        return all_events

    def _search(self, query: str, seen_urls: set[str]) -> list[HackathonEvent]:
        """Esegue una singola query sul CSE."""
        params = {
            "key": config.GOOGLE_CSE_API_KEY,
            "cx": config.GOOGLE_CSE_CX,
            "q": query,
            "num": 10,
            "dateRestrict": "m3",  # Ultimi 3 mesi
            "gl": "it",  # Geolocalizzazione: Italia
            "lr": "lang_it|lang_en",  # Risultati in italiano o inglese
        }

        data = safe_get_json(CSE_API_URL, params=params)
        if not data or not isinstance(data, dict):
            return []

        items = data.get("items", [])
        events: list[HackathonEvent] = []

        for item in items:
            url = item.get("link", "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            title = item.get("title", "").strip()
            snippet = item.get("snippet", "").strip()

            if not title:
                continue

            # Estrai metatag se disponibili
            metatags = {}
            pagemap = item.get("pagemap", {})
            metatag_list = pagemap.get("metatags", [{}])
            if metatag_list:
                metatags = metatag_list[0]

            # Cerca data nei metatag
            date_str = (
                metatags.get("event:start_date", "")
                or metatags.get("og:updated_time", "")
                or metatags.get("article:published_time", "")
                or ""
            )

            # Organizer dai metatag
            organizer = metatags.get("og:site_name", "")

            events.append(HackathonEvent(
                title=title,
                url=url,
                source=self.name,
                description=snippet,
                date_str=date_str,
                location=config.SEARCH_LOCATION,
                organizer=organizer,
            ))

        return events


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    collector = GoogleCSECollector()
    events = collector.collect()
    for e in events:
        print(f"  [{e.source}] {e.title} — {e.url}")
