"""Collector Web Search - meta-aggregatore via DuckDuckGo (ddgs).

Cerca "hackathon Milano" e varianti, completamente gratuito
e senza bisogno di API key. Sostituisce il Google CSE.

Query focalizzate e filtro URL per ridurre il rumore.
"""

import logging
import re
import time

import config
from models import BaseCollector, HackathonEvent

logger = logging.getLogger(__name__)

# Query di ricerca — focalizzate su eventi reali e pagine evento
SEARCH_QUERIES = [
    # ── Query generiche ──
    "hackathon Milano 2026",
    "hackathon Milan Italy 2026",
    "hackathon Milano 2025 2026",
    # ── Varianti formato ──
    "makeathon OR datathon OR ideathon Milano 2026",
    "startup weekend Milano 2026",
    "game jam Milano 2026",
    "coding challenge Milano 2026",
    "cybersecurity hackathon Milano 2026",
    # ── Italian multi-lingua ──
    "maratona di programmazione Milano 2026",
    "sfida digitale innovazione Milano 2026",
    "competizione coding Milano OR Lombardia 2026",
    # ── Piattaforme evento ──
    "site:eventbrite.it hackathon Milano",
    "site:eventbrite.com hackathon Milan",
    "site:lu.ma hackathon Milan",
    "site:devpost.com hackathon Milan Italy",
    "site:meetup.com hackathon Milano",
    "site:bo-om.it/news-ed-eventi hackathon Milano 2026",
    "site:bo-om.it/nttdata_hackathon IkigAIverse Milano 2026",
    # ── Hub innovazione ──
    "site:polihub.it hackathon",
    "site:cariplofactory.it hackathon",
    "site:fondazionetriulza.org hackathon",
    "site:telespazio.com hackathon Milano 2026",
]

# URL che NON sono pagine evento (listing, profili, wiki, ...)
# NOTA: NON blocchiamo post social (LinkedIn, Facebook) — possono contenere
# annunci di hackathon reali. Lasciamo che il LLM valuti il contenuto.
_NOISE_URL_PATTERNS = [
    re.compile(r"wiki.*/Main_Page", re.I),
    re.compile(r"wiki.*/Pagina_principale", re.I),
    re.compile(r"wikipedia\.org/wiki/", re.I),
    re.compile(r"/wiki/.+/(zh|nl|es|fr|de|ja|ko|pt|ru|ar|hi|he|pl|sv|da|ca|fi|no|cs|sk|hu|ro|tr|uk|vi|id|th|bn|ms)$", re.I),
    re.compile(r"/wiki/.+/Participants", re.I),
    re.compile(r"wiki\.wikimedia\.it/wiki/(Diario|Wikimedia_news)", re.I),
    re.compile(r"planet\.wikimedia\.org", re.I),
    re.compile(r"businesspeople\.it/", re.I),
    re.compile(r"/users?/[^/]+/?$", re.I),             # profile pages
    re.compile(r"eventbrite\.[a-z]+/d/", re.I),          # listing/search pages
    re.compile(r"allevents\.in/", re.I),                  # aggregatore rumoroso
    re.compile(r"stayhappening\.com/", re.I),             # aggregatore rumoroso
    re.compile(r"eventitech\.it/events/", re.I),           # aggregatore eventi tech: spesso cita altri eventi
    re.compile(r"hacktrack-eu\.vercel\.app", re.I),       # aggregatore EU hackathon listing
    re.compile(r"hackathon\.com/event/", re.I),             # aggregatore con date stale
    re.compile(r"devfolio\.co/", re.I),                     # quasi esclusivamente hackathon indiani
    re.compile(r"\d{4}\.lac\.tf", re.I),                    # LA CTF (Los Angeles)
    re.compile(r"foss\.events/", re.I),                     # conferenze FOSS
    re.compile(r"bo-om\.it/eb_aziende/?$", re.I),           # CTF/academy page, not hackathon listing
    re.compile(r"issapulire\.com/it/eventi/hackathon\.html", re.I),
    re.compile(r"lu\.ma/wow6yhnn", re.I),
    re.compile(r"lu\.ma/AiCreativeHackathon", re.I),
    re.compile(r"civilweek-vivere\.it/eventi/ideathon-2/?$", re.I),
    re.compile(r"globalgamejam\.it/milano/?$", re.I),
    re.compile(r"globalgamejam\.org/jam-sites/2026/milan-global-game-jam-2026-igda-milan-sae-institute/?$", re.I),
    re.compile(r"esp\.unimi\.it/it/eventi/ecohackathon-2026/?$", re.I),
    re.compile(r"zero\.eu/en/eventi/136252-global-game-jam-4,milano/?$", re.I),
    re.compile(r"levillagebyca\.it/it/community-hackathon-by-ca/?$", re.I),
    re.compile(r"fastweb\.it/fastwebai-hackathon/?$", re.I),
    re.compile(r"\.(pdf|doc|docx|ppt|pptx)$", re.I),     # documenti
    re.compile(r"youtube\.com/watch", re.I),
]


def _is_noise_url(url: str) -> bool:
    """Ritorna True se l'URL è probabilmente NON una pagina evento."""
    return any(p.search(url) for p in _NOISE_URL_PATTERNS)


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

        for i, query in enumerate(SEARCH_QUERIES):
            if i > 0:
                time.sleep(2)  # Pausa tra query per evitare rate limit
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
                max_results=20,
            ))
        except Exception as e:
            logger.warning("Errore DuckDuckGo per query '%s': %s", query, e)
            return []

        events: list[HackathonEvent] = []

        for item in results:
            url = item.get("href", "").strip()
            if not url or url in seen_urls:
                continue

            # Filtra URL rumorosi (post social, listing, profili, articoli)
            if _is_noise_url(url):
                logger.debug("Scartato URL rumoroso: %s", url)
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
                location="",  # Non sappiamo la location reale
            ))

        return events


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    collector = WebSearchCollector()
    events = collector.collect()
    for e in events:
        print(f"  [{e.source}] {e.title} — {e.url}")
