"""
Collector per GDG (Google Developer Groups) Community — gdg.community.dev

Strategia:
1. Scrape delle pagine capitolo GDG di Milano per ottenere gli URL degli eventi.
2. Fetch delle pagine di dettaglio evento per estrarre JSON-LD strutturato
   (schema.org Event) con titolo, date, location, descrizione.
"""

import json
import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from models import BaseCollector, HackathonEvent
from utils.http import safe_get

logger = logging.getLogger(__name__)

# Capitoli GDG nell'area di Milano
GDG_CHAPTER_URLS = [
    "https://gdg.community.dev/gdg-milano/",
    "https://gdg.community.dev/gdg-cloud-milano/",
    "https://gdg.community.dev/gdg-on-campus-polytechnic-university-of-milan/",
]

_EVENT_DETAIL_RE = re.compile(r"/events/details/[^/]+/$")


class GDGCollector(BaseCollector):
    """Raccoglie eventi dai Google Developer Groups (gdg.community.dev)."""

    @property
    def name(self) -> str:
        return "gdg_community"

    def collect(self) -> list[HackathonEvent]:
        event_urls = self._discover_event_urls()
        logger.info("GDG: %d URL evento unici trovati", len(event_urls))

        events: list[HackathonEvent] = []
        for url in event_urls:
            event = self._fetch_event_detail(url)
            if event:
                events.append(event)

        logger.info("GDG: %d eventi totali raccolti", len(events))
        return events

    # ── Fase 1: scoperta URL eventi dalle pagine capitolo ──

    def _discover_event_urls(self) -> list[str]:
        """Scrape delle pagine capitolo per trovare link a eventi."""
        seen: set[str] = set()
        urls: list[str] = []

        for chapter_url in GDG_CHAPTER_URLS:
            try:
                resp = safe_get(chapter_url)
                if not resp:
                    continue
                soup = BeautifulSoup(resp.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    # Normalizza: rimuovi suffissi /cohost-*
                    clean = re.sub(r"/cohost-[^/]+$", "/", href)
                    if not _EVENT_DETAIL_RE.search(clean):
                        continue
                    # Assicura URL assoluto
                    if clean.startswith("/"):
                        clean = "https://gdg.community.dev" + clean
                    if clean not in seen:
                        seen.add(clean)
                        urls.append(clean)
            except Exception as e:
                logger.warning("GDG chapter %s fallito: %s", chapter_url, e)

        return urls

    # ── Fase 2: fetch dettaglio evento + parse JSON-LD ──

    def _fetch_event_detail(self, url: str) -> HackathonEvent | None:
        """Scarica la pagina dettaglio di un evento ed estrae JSON-LD."""
        try:
            resp = safe_get(url)
            if not resp:
                return None
            soup = BeautifulSoup(resp.text, "html.parser")

            # Cerca JSON-LD (schema.org Event)
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(script.string)
                except (json.JSONDecodeError, TypeError):
                    continue
                if data.get("@type") != "Event":
                    continue
                return self._parse_jsonld(data, url)

            # Fallback: estrai da meta tag OG
            return self._parse_meta(soup, url)

        except Exception as e:
            logger.debug("GDG: errore fetch %s: %s", url, e)
            return None

    def _parse_jsonld(self, data: dict, url: str) -> HackathonEvent | None:
        """Parse struttura JSON-LD schema.org/Event."""
        title = data.get("name", "").strip()
        if not title:
            return None

        description = data.get("description", "")
        start = data.get("startDate", "")

        # Location
        loc = data.get("location", {})
        location = ""
        if isinstance(loc, dict):
            place_name = loc.get("name", "")
            address = loc.get("address", "")
            if isinstance(address, dict):
                address = address.get("streetAddress", "")
            location = ", ".join(p for p in [place_name, address] if p) or ""

        # Organizer
        org = data.get("organizer", {})
        organizer = org.get("name", "") if isinstance(org, dict) else ""

        date_str = ""
        if start:
            try:
                dt = datetime.fromisoformat(start)
                date_str = dt.strftime("%d %b %Y")
            except (ValueError, TypeError):
                date_str = start

        return HackathonEvent(
            title=title,
            url=url,
            source=self.name,
            description=description,
            date_str=date_str,
            location=location,
            organizer=organizer or "Google Developer Groups",
        )

    def _parse_meta(self, soup: BeautifulSoup, url: str) -> HackathonEvent | None:
        """Fallback: estrai info da meta tag OpenGraph."""
        title = ""
        description = ""
        og_title = soup.find("meta", property="og:title")
        if og_title:
            title = og_title.get("content", "").replace(" | Google Developer Groups", "").strip()
        og_desc = soup.find("meta", property="og:description")
        if og_desc:
            description = og_desc.get("content", "")
        meta_desc = soup.find("meta", attrs={"name": "description"})
        date_str = ""
        if meta_desc:
            content = meta_desc.get("content", "")
            # Pattern: "... presents TITLE | May 9, 2026. ..."
            m = re.search(r"\|\s*(\w+ \d{1,2},\s*\d{4})", content)
            if m:
                date_str = m.group(1)

        if not title:
            return None

        return HackathonEvent(
            title=title,
            url=url,
            source=self.name,
            description=description,
            date_str=date_str,
            location="Milano",
            organizer="Google Developer Groups",
        )
