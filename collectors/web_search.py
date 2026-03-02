"""Collector Web Search - meta-aggregatore via DuckDuckGo (ddgs).

Cerca "hackathon Milano" e varianti, completamente gratuito
e senza bisogno di API key. Sostituisce il Google CSE.

Usa ~6 query per run, nessun limite giornaliero rigido.
"""

import logging

import config
from models import BaseCollector, HackathonEvent

logger = logging.getLogger(__name__)

# Query di ricerca — varianti per massimizzare la copertura
SEARCH_QUERIES = [
    # ── Query generiche IT / EN ──
    "hackathon Milano 2026 evento",
    "hackathon Milan Italy 2026 event",
    "coding challenge hackathon Milano iscrizione",
    "hackathon Politecnico Milano OR Bocconi 2026",
    # ── Varianti di formato ──
    "makeathon OR datathon OR ideathon Milano 2026",
    "startup weekend Milano 2026",
    "game jam Milano 2026",
    "innovation challenge tech challenge Milano 2026",
    # ── Piattaforme specifiche ──
    "site:eventbrite.it hackathon Milano",
    "site:lu.ma hackathon Milan",
    "site:devpost.com hackathon Milan",
    "site:meetup.com hackathon Milano",
    # ── Hackathon.com e piattaforme challenge ──
    "site:hackathon.com Milano Italy",
    "site:taikai.network hackathon Milano",
    "site:codemotion.com hackathon Milano",
    "site:agorize.com hackathon Milano",
    "site:bemyapp.com hackathon Milano",
    # ── Hub e spazi innovazione Milano ──
    "site:talentgarden.it hackathon Milano",
    "site:cariplofactory.it hackathon",
    "site:levillagebyca.com hackathon Milano",
    "site:fintechdistrict.com hackathon Milano",
    "site:openinnovation.regione.lombardia.it hackathon",
    # ── LinkedIn ──
    "site:linkedin.com hackathon Milano 2026",
    "linkedin.com/posts hackathon Milano",
]


class WebSearchCollector(BaseCollector):

    @property
    def name(self) -> str:
        return "web_search"

    def collect(self) -> list[HackathonEvent]:
        try:
            from ddgs import DDGS
        except ImportError:
            logger.warning("ddgs non installato — skip collector web_search")
            return []

        all_events: list[HackathonEvent] = []
        seen_urls: set[str] = set()

        for query in SEARCH_QUERIES:
            events = self._search(query, seen_urls)
            all_events.extend(events)

        logger.info("Web Search: trovati %d risultati totali", len(all_events))
        return all_events

    def _search(self, query: str, seen_urls: set[str]) -> list[HackathonEvent]:
        """Esegue una singola query su DuckDuckGo."""
        try:
            from ddgs import DDGS

            ddgs = DDGS()
            results = list(ddgs.text(
                query,
                region="it-it",
                max_results=10,
            ))
        except Exception as e:
            logger.warning("Errore DuckDuckGo per query '%s': %s", query, e)
            return []

        events: list[HackathonEvent] = []

        for item in results:
            url = item.get("href", "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            title = item.get("title", "").strip()
            body = item.get("body", "").strip()

            if not title:
                continue

            events.append(HackathonEvent(
                title=title,
                url=url,
                source=self.name,
                description=body,
                location=config.SEARCH_LOCATION,
            ))

        return events


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    collector = WebSearchCollector()
    events = collector.collect()
    for e in events:
        print(f"  [{e.source}] {e.title} — {e.url}")
