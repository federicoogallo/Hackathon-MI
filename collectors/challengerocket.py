"""
Collector ChallengeRocket — scraping pagina hackathon/challenges.

Focus EU/CEE. Scraping HTML delle card.
URL: https://challengerocket.com/hackathons
"""

import logging

from bs4 import BeautifulSoup

import config
from models import BaseCollector, HackathonEvent
from utils.http import safe_get

logger = logging.getLogger(__name__)

CHALLENGEROCKET_URLS = [
    "https://challengerocket.com/hackathons",
    "https://challengerocket.com/challenges",
]

ITALY_KEYWORDS = {"italy", "italia", "milan", "milano", "europe", "europa"}


class ChallengeRocketCollector(BaseCollector):

    @property
    def name(self) -> str:
        return "challengerocket"

    def collect(self) -> list[HackathonEvent]:
        all_events: list[HackathonEvent] = []
        seen_urls: set[str] = set()

        for url in CHALLENGEROCKET_URLS:
            response = safe_get(url)
            if response is None:
                continue
            events = self._parse_html(response.text, seen_urls)
            all_events.extend(events)

        logger.info("ChallengeRocket: trovati %d eventi", len(all_events))
        return all_events

    def _parse_html(self, html: str, seen_urls: set[str]) -> list[HackathonEvent]:
        """Parsa le card di ChallengeRocket."""
        soup = BeautifulSoup(html, "lxml")
        events: list[HackathonEvent] = []

        cards = soup.find_all("div", class_=lambda c: c and ("challenge" in str(c).lower() or "hackathon" in str(c).lower() or "card" in str(c).lower()))
        if not cards:
            cards = soup.find_all("article")

        for card in cards:
            event = self._parse_card(card, seen_urls)
            if event:
                events.append(event)

        # Fallback
        if not events:
            links = soup.find_all("a", href=lambda h: h and ("/hackathon" in h or "/challenge" in h))
            for link in links:
                href = link.get("href", "").strip()
                title = link.get_text(strip=True)
                if not href or not title or len(title) < 5 or href in seen_urls:
                    continue
                if not href.startswith("http"):
                    href = f"https://challengerocket.com{href}"
                seen_urls.add(href)

                events.append(HackathonEvent(
                    title=title,
                    url=href,
                    source=self.name,
                ))

        return events

    def _parse_card(self, card, seen_urls: set[str]) -> HackathonEvent | None:
        """Estrae un evento da una card."""
        try:
            link = card.find("a", href=True)
            if not link:
                return None

            url = link.get("href", "").strip()
            if not url:
                return None
            if not url.startswith("http"):
                url = f"https://challengerocket.com{url}"
            if url in seen_urls:
                return None
            seen_urls.add(url)

            title_el = card.find(["h2", "h3", "h4"])
            title = title_el.get_text(strip=True) if title_el else link.get_text(strip=True)
            if not title or len(title) < 3:
                return None

            date_el = card.find(class_=lambda c: c and "date" in str(c).lower())
            date_str = date_el.get_text(strip=True) if date_el else ""

            loc_el = card.find(class_=lambda c: c and ("location" in str(c).lower() or "place" in str(c).lower()))
            location = loc_el.get_text(strip=True) if loc_el else ""

            desc_el = card.find(class_=lambda c: c and ("desc" in str(c).lower() or "summary" in str(c).lower()))
            description = desc_el.get_text(strip=True)[:500] if desc_el else ""

            return HackathonEvent(
                title=title,
                url=url,
                source=self.name,
                description=description,
                date_str=date_str,
                location=location or "",
            )
        except Exception as e:
            logger.debug("ChallengeRocket parse error: %s", e)
            return None
