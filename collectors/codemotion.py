"""
Collector Codemotion — scraping community.codemotion.com.

La più grande community tech italiana. Organizza hackathon propri e
aggrega eventi della community. Scraping HTML della pagina eventi.
"""

import logging

from bs4 import BeautifulSoup

import config
from models import BaseCollector, HackathonEvent
from utils.http import safe_get

logger = logging.getLogger(__name__)

CODEMOTION_URLS = [
    "https://community.codemotion.com/events",
    "https://www.codemotion.com/events",
    "https://community.codemotion.com/hackathons",
]


class CodemotionCollector(BaseCollector):

    @property
    def name(self) -> str:
        return "codemotion"

    def collect(self) -> list[HackathonEvent]:
        all_events: list[HackathonEvent] = []
        seen_urls: set[str] = set()

        for url in CODEMOTION_URLS:
            response = safe_get(url)
            if response is None:
                continue
            events = self._parse_html(response.text, url, seen_urls)
            all_events.extend(events)

        logger.info("Codemotion: trovati %d eventi", len(all_events))
        return all_events

    def _parse_html(self, html: str, base_url: str, seen_urls: set[str]) -> list[HackathonEvent]:
        """Parsa la pagina eventi di Codemotion."""
        soup = BeautifulSoup(html, "lxml")
        events: list[HackathonEvent] = []

        # Codemotion usa card per gli eventi
        cards = soup.find_all("div", class_=lambda c: c and ("event" in str(c).lower() or "card" in str(c).lower()))
        if not cards:
            cards = soup.find_all("article")
        if not cards:
            cards = soup.find_all("li", class_=lambda c: c and "event" in str(c).lower())

        for card in cards:
            event = self._parse_card(card, base_url, seen_urls)
            if event:
                events.append(event)

        # Fallback: link generici a eventi
        if not events:
            links = soup.find_all("a", href=lambda h: h and ("event" in h.lower() or "hackathon" in h.lower()))
            for link in links:
                href = link.get("href", "").strip()
                title = link.get_text(strip=True)
                if not href or not title or len(title) < 5 or href in seen_urls:
                    continue
                if not href.startswith("http"):
                    from urllib.parse import urljoin
                    href = urljoin(base_url, href)
                seen_urls.add(href)

                events.append(HackathonEvent(
                    title=title,
                    url=href,
                    source=self.name,
                    location="",
                ))

        return events

    def _parse_card(self, card, base_url: str, seen_urls: set[str]) -> HackathonEvent | None:
        """Estrae un evento da una card Codemotion."""
        try:
            link = card.find("a", href=True)
            if not link:
                return None

            url = link.get("href", "").strip()
            if not url:
                return None
            if not url.startswith("http"):
                from urllib.parse import urljoin
                url = urljoin(base_url, url)
            if url in seen_urls:
                return None
            seen_urls.add(url)

            # Titolo
            title_el = card.find(["h2", "h3", "h4", "h5"])
            title = title_el.get_text(strip=True) if title_el else link.get_text(strip=True)
            if not title or len(title) < 3:
                return None

            # Data
            date_el = card.find(["time"]) or card.find(class_=lambda c: c and "date" in str(c).lower())
            date_str = ""
            if date_el:
                date_str = date_el.get("datetime", "") or date_el.get_text(strip=True)

            # Location
            loc_el = card.find(class_=lambda c: c and ("location" in str(c).lower() or "venue" in str(c).lower()))
            location = loc_el.get_text(strip=True) if loc_el else ""

            # Description
            desc_el = card.find(class_=lambda c: c and ("desc" in str(c).lower() or "summary" in str(c).lower() or "text" in str(c).lower()))
            description = desc_el.get_text(strip=True)[:500] if desc_el else ""

            return HackathonEvent(
                title=title,
                url=url,
                source=self.name,
                description=description,
                date_str=date_str,
                location=location,
                organizer="Codemotion",
            )
        except Exception as e:
            logger.debug("Codemotion card parse error: %s", e)
            return None
