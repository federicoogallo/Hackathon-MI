"""
Collector Taikai.network — hackathon globali aperti.

Strategia: scraping HTML del listato hackathon (senza API key).
Funziona in GitHub Actions perché non dipende da DuckDuckGo/DDGS.
Nota: gli hackathon su Taikai sono per lo più internazionali/online.
"""

import logging
import re

from bs4 import BeautifulSoup

from models import BaseCollector, HackathonEvent
from utils.http import safe_get

logger = logging.getLogger(__name__)

TAIKAI_URL = "https://taikai.network/en/hackathons?status=open"
TAIKAI_BASE = "https://taikai.network"

# Pattern per link alle singole pagine hackathon: /en/{org}/hackathons/{slug}
_HACK_HREF_RE = re.compile(r"^/en/[^/]+/hackathons/[^/]+/?$")

# Status che indicano un hackathon già concluso (da scartare)
_FINISHED_STATUS_RE = re.compile(
    r"^(Finished|Winners Announced|Ended|Closed)",
    re.IGNORECASE,
)


class TaikaiCollector(BaseCollector):
    """Scraper del listato hackathon di Taikai.network."""

    @property
    def name(self) -> str:
        return "taikai"

    def collect(self) -> list[HackathonEvent]:
        response = safe_get(TAIKAI_URL, timeout=15)
        if response is None:
            logger.error("Taikai: impossibile raggiungere %s", TAIKAI_URL)
            return []

        if response.status_code != 200:
            logger.warning("Taikai: HTTP %d", response.status_code)
            return []

        soup = BeautifulSoup(response.text, "lxml")
        events = self._parse_hackathons(soup)
        logger.info("Taikai: trovati %d hackathon", len(events))
        return events

    def _parse_hackathons(self, soup: BeautifulSoup) -> list[HackathonEvent]:
        events: list[HackathonEvent] = []
        seen: set[str] = set()

        for a_tag in soup.find_all("a", href=True):
            href = a_tag.get("href", "")
            if not _HACK_HREF_RE.match(href):
                continue

            full_url = f"{TAIKAI_BASE}{href}"
            if full_url in seen:
                continue
            seen.add(full_url)

            raw_text = a_tag.get_text(" ", strip=True)

            # Salta hackathon già conclusi
            if _FINISHED_STATUS_RE.match(raw_text):
                logger.debug("Taikai: skip (Finished) %s", href)
                continue

            # Estrai titolo dall'<h3> interno (struttura Taikai)
            h3 = a_tag.find("h3")
            if h3:
                title = h3.get_text(" ", strip=True)
            else:
                title = self._extract_title(raw_text, href)

            if not title:
                continue

            # Descrizione: cerca il div che segue l'h3
            description = ""
            if h3:
                next_div = h3.find_next_sibling()
                if next_div:
                    description = next_div.get_text(" ", strip=True)[:300]
            if not description:
                description = self._extract_description(raw_text, title)

            events.append(
                HackathonEvent(
                    title=title,
                    url=full_url,
                    source=self.name,
                    description=description,
                    location="Online / Internazionale",
                )
            )

        return events

    def _extract_title(self, raw_text: str, href: str) -> str:
        """Estrae il titolo dal testo ancora / dal slug."""
        text = raw_text

        # Rimuovi prefissi di status (es: "Registrations are open", "Registration -")
        text = re.sub(
            r"^(Finished|Winners Announced|Registrations?\s+are\s+open"
            r"|Registrations?\s+open|Registration\s*[-–]?\s*"
            r"|Open(?:\s+for\s+Submissions?)?"
            r"|Coming Soon|Ongoing)\s*",
            "",
            text,
            flags=re.IGNORECASE,
        ).strip()

        # Rimuovi coppie di numeri iniziali tipo "62 34" (partecipanti/team), con spazio iniziale
        text = re.sub(r"^\s*\d+\s+\d+\s+", "", text).strip()

        # Prendi i primi ~80 caratteri come titolo (prima della descrizione)
        # Spesso il titolo è seguito da una frase descrittiva
        title = text[:80].strip()

        # Fallback: usa il slug convertito
        if len(title) < 5:
            slug = href.rstrip("/").split("/")[-1]
            title = slug.replace("-", " ").title()

        return title

    def _extract_description(self, raw_text: str, title: str) -> str:
        """Estrae la descrizione (testo dopo il titolo)."""
        if title and title[:20] in raw_text:
            idx = raw_text.find(title[:20])
            remainder = raw_text[idx + len(title):].strip()
            return remainder[:300]
        return ""


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    collector = TaikaiCollector()
    events = collector.collect()
    print(f"Totale: {len(events)}")
    for e in events:
        print(f"  {e.title}")
        print(f"    {e.url}")
