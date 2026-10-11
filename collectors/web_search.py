"""Collector Web Search - meta-aggregatore via DuckDuckGo (ddgs).

Cerca "hackathon Milano" e varianti, completamente gratuito
e senza bisogno di API key. Sostituisce il Google CSE.

Query focalizzate e filtro URL per ridurre il rumore.
"""

import logging
import re
import time
from datetime import date

from models import BaseCollector, HackathonEvent
from utils.collector_health import record_issue
from utils.event_evidence import enrich_event_evidence, is_promising_result

logger = logging.getLogger(__name__)

MAX_EVIDENCE_PAGES = 8


def build_search_queries(today: date | None = None) -> list[str]:
    """Keep broad discovery current and cover student/community announcements."""
    year = (today or date.today()).year
    return [
        f"hackathon Milano {year}",
        f"hackathon Milan Italy {year}",
        f"hackathon Milano {year + 1}",
        f"hackathon Milan Italy {year + 1}",
        f"makeathon OR datathon OR ideathon Milano {year}",
        f"startup weekend Milano {year}",
        f"game jam Milano {year}",
        f"coding challenge Milano {year}",
        f"cybersecurity hackathon Milano {year}",
        f"maratona di programmazione Milano {year}",
        f"sfida digitale innovazione Milano {year}",
        f"competizione coding Milano OR Lombardia {year}",
        "site:eventbrite.it hackathon Milano",
        "site:eventbrite.com hackathon Milan",
        "site:lu.ma hackathon Milan",
        "site:luma.com hackathon Milan",
        "site:devpost.com hackathon Milan Italy",
        "site:meetup.com hackathon Milano",
        f"site:bo-om.it/news-ed-eventi hackathon Milano {year}",
        "site:polihub.it hackathon",
        "site:cariplofactory.it hackathon",
        "site:fondazionetriulza.org hackathon",
        f"site:telespazio.com hackathon Milano {year}",
        f"site:unibocconi.it hackathon {year}",
        f"Bocconi BAINSA hackathon {year}",
        f"Anthropic Claude hackathon Milan {year}",
        "site:luma.com Bocconi hackathon",
        "site:lu.ma BAINSA hackathon",
        f"associazioni studentesche hackathon Milano {year}",
    ]


def evidence_candidates(events: list[HackathonEvent], today: date | None = None) -> list[HackathonEvent]:
    """Rotate the small fetch budget daily, reserving space for community sources."""
    day = (today or date.today()).toordinal()
    candidates = sorted((event for event in events if is_promising_result(event)), key=lambda event: event.url)
    if not candidates:
        return []
    community = [event for event in candidates if re.search(
        r"bocconi|bainsa|anthropic", f"{event.title} {event.description} {event.url}", re.I
    )]
    if community:
        offset = day % len(community)
        community = community[offset:] + community[:offset]
    reserved = community[:2]
    remaining = [event for event in candidates if event not in reserved]
    if remaining:
        offset = day % len(remaining)
        remaining = remaining[offset:] + remaining[:offset]
    return (reserved + remaining)[:MAX_EVIDENCE_PAGES]

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
    re.compile(r"instagram\.com/reel/DNne53iIqc2", re.I),
    re.compile(r"events\.raspberrypi\.com/community/6f41b7d6-d731-4376-acf5-c5b5dddb038c", re.I),
    re.compile(r"meta\.wikimedia\.org/wiki/Event:Hardware_tools_for_Wiki/Raspberry_JAM_at_Wikimedia_Hackathon_Milan_2026", re.I),
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
            record_issue("disabled", "ddgs is not installed")
            return []

        all_events: list[HackathonEvent] = []
        seen_urls: set[str] = set()

        for i, query in enumerate(build_search_queries()):
            if i > 0:
                time.sleep(2)  # Pausa tra query per evitare rate limit
            events = self._search(query, seen_urls)
            all_events.extend(events)

        candidates = evidence_candidates(all_events)
        enriched = sum(enrich_event_evidence(event) for event in candidates)
        logger.info("Web Search: pagine approfondite %d/%d", enriched, len(candidates))
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
            record_issue("error", f"Search query failed: {query}")
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
