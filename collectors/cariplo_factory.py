"""
Collector Cariplo Factory — scraping pagina eventi.

Cariplo Factory (Fondazione Cariplo) è un hub d'innovazione milanese
che organizza hackathon corporate e challenge d'innovazione.
URL: https://www.cariplofactory.it/eventi/
"""

import logging

from bs4 import BeautifulSoup

import config
from models import BaseCollector, HackathonEvent
from utils.http import safe_get

logger = logging.getLogger(__name__)

CARIPLO_URL = "https://www.cariplofactory.it/eventi/"


class CariploFactoryCollector(BaseCollector):

    @property
    def name(self) -> str:
        return "cariplo_factory"

    def collect(self) -> list[HackathonEvent]:
        response = safe_get(CARIPLO_URL)
        if response is None:
            logger.error("Cariplo Factory: impossibile raggiungere %s", CARIPLO_URL)
            return []

        events = self._parse_html(response.text)
        logger.info("Cariplo Factory: trovati %d eventi", len(events))
        return events

    def _parse_html(self, html: str) -> list[HackathonEvent]:
        """Parsa la pagina eventi di Cariplo Factory."""
        soup = BeautifulSoup(html, "lxml")
        events: list[HackathonEvent] = []
        seen_urls: set[str] = set()

        # Cerca card evento
        cards = soup.find_all("article")
        if not cards:
            cards = soup.find_all("div", class_=lambda c: c and ("event" in str(c).lower() or "post" in str(c).lower() or "card" in str(c).lower()))

        for card in cards:
            event = self._parse_card(card, seen_urls)
            if event:
                events.append(event)

        # Fallback: link a pagine interne con keyword rilevanti
        if not events:
            links = soup.find_all("a", href=lambda h: h and "cariplofactory.it" in h)
            for link in links:
                title = link.get_text(strip=True)
                href = link.get("href", "")
                if not title or not href or href in seen_urls or len(title) < 5:
                    continue
                seen_urls.add(href)

                events.append(HackathonEvent(
                    title=title,
                    url=href,
                    source=self.name,
                    location="Milano",
                    organizer="Cariplo Factory",
                ))

        return events

    def _parse_card(self, card, seen_urls: set[str]) -> HackathonEvent | None:
        """Estrae un evento da una card."""
        try:
            link = card.find("a", href=True)
            if not link:
                return None

            url = link.get("href", "").strip()
            if not url or url in seen_urls:
                return None
            if not url.startswith("http"):
                url = f"https://www.cariplofactory.it{url}"
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

            # Description
            desc_el = card.find(class_=lambda c: c and ("excerpt" in str(c).lower() or "desc" in str(c).lower() or "content" in str(c).lower()))
            description = desc_el.get_text(strip=True)[:500] if desc_el else ""

            return HackathonEvent(
                title=title,
                url=url,
                source=self.name,
                description=description,
                date_str=date_str,
                location="Milano",
                organizer="Cariplo Factory",
            )
        except Exception as e:
            logger.debug("Cariplo Factory parse error: %s", e)
            return None
