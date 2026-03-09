"""
Collector Startup Italia — scraping/RSS pagina eventi.

StartupItalia (startupitalia.eu) è il media di riferimento per
l'ecosistema startup italiano. Pubblica una sezione eventi con
hackathon, competition e challenge.
"""

import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime

from bs4 import BeautifulSoup

import config
from models import BaseCollector, HackathonEvent
from utils.http import safe_get

_YEAR_RE = re.compile(r'\b(20[0-9]{2})\b')

logger = logging.getLogger(__name__)

STARTUP_ITALIA_URLS = [
    "https://startupitalia.eu/eventi",
    "https://startupitalia.eu/tag/hackathon",
]

# RSS feed se disponibile
RSS_URLS = [
    "https://startupitalia.eu/feed",
]


class StartupItaliaCollector(BaseCollector):

    @property
    def name(self) -> str:
        return "startup_italia"

    def collect(self) -> list[HackathonEvent]:
        all_events: list[HackathonEvent] = []
        seen_urls: set[str] = set()

        # Prova RSS per primo (più strutturato)
        for rss_url in RSS_URLS:
            events = self._collect_rss(rss_url, seen_urls)
            all_events.extend(events)

        # Poi HTML
        for url in STARTUP_ITALIA_URLS:
            response = safe_get(url)
            if response is None:
                continue
            events = self._parse_html(response.text, url, seen_urls)
            all_events.extend(events)

        logger.info("Startup Italia: trovati %d eventi", len(all_events))
        return all_events

    def _collect_rss(self, rss_url: str, seen_urls: set[str]) -> list[HackathonEvent]:
        """Parsa il feed RSS per trovare articoli su hackathon."""
        response = safe_get(rss_url)
        if response is None:
            return []

        events: list[HackathonEvent] = []
        try:
            root = ET.fromstring(response.text)
            # Standard RSS 2.0
            for item in root.iter("item"):
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                desc = (item.findtext("description") or "").strip()
                pub_date = (item.findtext("pubDate") or "").strip()

                if not title or not link or link in seen_urls:
                    continue

                # Filtra solo articoli rilevanti (hackathon/challenge/competition)
                text_to_check = f"{title} {desc}".lower()
                hackathon_keywords = ["hackathon", "hack", "challenge", "competition", "maratona", "coding", "makeathon"]
                if not any(kw in text_to_check for kw in hackathon_keywords):
                    continue

                # Scarta articoli pubblicati in anni passati
                if pub_date:
                    current_year = datetime.now().year
                    years = [int(y) for y in _YEAR_RE.findall(pub_date)]
                    if years and all(y < current_year for y in years):
                        logger.debug("RSS skip articolo vecchio (%s): %s", pub_date, title[:60])
                        continue

                seen_urls.add(link)
                events.append(HackathonEvent(
                    title=title,
                    url=link,
                    source=self.name,
                    description=BeautifulSoup(desc, "lxml").get_text(strip=True)[:500] if desc else "",
                    date_str=pub_date,
                    location="",
                    organizer="Startup Italia",
                ))
        except ET.ParseError as e:
            logger.debug("Startup Italia RSS parse error: %s", e)

        return events

    def _parse_html(self, html: str, base_url: str, seen_urls: set[str]) -> list[HackathonEvent]:
        """Parsa la pagina eventi/tag di Startup Italia."""
        soup = BeautifulSoup(html, "lxml")
        events: list[HackathonEvent] = []

        # Cerca article o card
        cards = soup.find_all("article")
        if not cards:
            cards = soup.find_all("div", class_=lambda c: c and ("post" in str(c).lower() or "card" in str(c).lower() or "event" in str(c).lower()))

        for card in cards:
            event = self._parse_card(card, base_url, seen_urls)
            if event:
                events.append(event)

        return events

    def _parse_card(self, card, base_url: str, seen_urls: set[str]) -> HackathonEvent | None:
        """Estrae un evento/articolo da una card."""
        try:
            link = card.find("a", href=True)
            if not link:
                return None

            url = link.get("href", "").strip()
            if not url or url in seen_urls:
                return None
            if not url.startswith("http"):
                from urllib.parse import urljoin
                url = urljoin(base_url, url)
            seen_urls.add(url)

            title_el = card.find(["h2", "h3", "h4"])
            title = title_el.get_text(strip=True) if title_el else link.get_text(strip=True)
            if not title or len(title) < 3:
                return None

            # Data
            date_el = card.find(["time"]) or card.find(class_=lambda c: c and "date" in str(c).lower())
            date_str = ""
            if date_el:
                date_str = date_el.get("datetime", "") or date_el.get_text(strip=True)

            # Scarta card con data di pubblicazione in anni passati
            if date_str:
                current_year = datetime.now().year
                years = [int(y) for y in _YEAR_RE.findall(date_str)]
                if years and all(y < current_year for y in years):
                    logger.debug("HTML skip articolo vecchio (%s): %s", date_str, title[:60])
                    return None

            # Description
            desc_el = card.find(class_=lambda c: c and ("excerpt" in str(c).lower() or "desc" in str(c).lower() or "summary" in str(c).lower()))
            description = desc_el.get_text(strip=True)[:500] if desc_el else ""

            return HackathonEvent(
                title=title,
                url=url,
                source=self.name,
                description=description,
                date_str=date_str,
                location="",
                organizer="Startup Italia",
            )
        except Exception as e:
            logger.debug("Startup Italia card parse error: %s", e)
            return None
