"""
Collector HackerEarth — scraping pagina challenges.

URL: https://www.hackerearth.com/challenges/
Mix online + onsite. Scraping HTML delle card challenge.
"""

import logging

from bs4 import BeautifulSoup

import config
from models import BaseCollector, HackathonEvent
from utils.http import safe_get

logger = logging.getLogger(__name__)

HACKEREARTH_URLS = [
    "https://www.hackerearth.com/challenges/hackathon/",
    "https://www.hackerearth.com/challenges/?type=hackathon",
]

ITALY_KEYWORDS = {"italy", "italia", "milan", "milano", "europe", "europa"}


class HackerEarthCollector(BaseCollector):

    @property
    def name(self) -> str:
        return "hackerearth"

    def collect(self) -> list[HackathonEvent]:
        all_events: list[HackathonEvent] = []
        seen_urls: set[str] = set()

        for url in HACKEREARTH_URLS:
            response = safe_get(url)
            if response is None:
                continue
            events = self._parse_html(response.text, seen_urls)
            all_events.extend(events)

        logger.info("HackerEarth: trovati %d eventi", len(all_events))
        return all_events

    def _parse_html(self, html: str, seen_urls: set[str]) -> list[HackathonEvent]:
        """Parsa la pagina challenges di HackerEarth."""
        soup = BeautifulSoup(html, "lxml")
        events: list[HackathonEvent] = []

        # HackerEarth usa card per le challenge
        cards = soup.find_all("div", class_=lambda c: c and ("challenge" in str(c).lower() or "hackathon" in str(c).lower() or "card" in str(c).lower()))
        if not cards:
            cards = soup.find_all("article")

        for card in cards:
            event = self._parse_card(card, seen_urls)
            if event:
                events.append(event)

        # Fallback: link generici
        if not events:
            links = soup.find_all("a", href=lambda h: h and "/challenge/" in h or (h and "/hackathon/" in h))
            for link in links:
                href = link.get("href", "").strip()
                title = link.get_text(strip=True)
                if not href or not title or len(title) < 5 or href in seen_urls:
                    continue
                if not href.startswith("http"):
                    href = f"https://www.hackerearth.com{href}"
                seen_urls.add(href)

                events.append(HackathonEvent(
                    title=title,
                    url=href,
                    source=self.name,
                ))

        return events

    def _parse_card(self, card, seen_urls: set[str]) -> HackathonEvent | None:
        """Estrae un evento da una card HackerEarth."""
        try:
            link = card.find("a", href=True)
            if not link:
                return None

            url = link.get("href", "").strip()
            if not url:
                return None
            if not url.startswith("http"):
                url = f"https://www.hackerearth.com{url}"
            if url in seen_urls:
                return None
            seen_urls.add(url)

            title_el = card.find(["h2", "h3", "h4"])
            title = title_el.get_text(strip=True) if title_el else link.get_text(strip=True)
            if not title or len(title) < 3:
                return None

            # Date
            date_el = card.find(class_=lambda c: c and ("date" in str(c).lower() or "time" in str(c).lower()))
            date_str = date_el.get_text(strip=True) if date_el else ""

            # Location
            loc_el = card.find(class_=lambda c: c and "location" in str(c).lower())
            location = loc_el.get_text(strip=True) if loc_el else ""

            # Description
            desc_el = card.find(class_=lambda c: c and ("desc" in str(c).lower() or "detail" in str(c).lower()))
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
            logger.debug("HackerEarth card parse error: %s", e)
            return None
