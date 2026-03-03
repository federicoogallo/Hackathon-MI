"""
Collector Hackathon.com — scraping pagina hackathon per Milan/Italy.

URL: https://www.hackathon.com/city/italy/milan
Aggregatore dedicato. HTML scraping delle card evento.
"""

import logging

from bs4 import BeautifulSoup

import config
from models import BaseCollector, HackathonEvent
from utils.http import safe_get

logger = logging.getLogger(__name__)

HACKATHON_COM_URLS = [
    "https://www.hackathon.com/city/italy/milan",
    "https://www.hackathon.com/country/italy",
]


class HackathonComCollector(BaseCollector):

    @property
    def name(self) -> str:
        return "hackathon_com"

    def collect(self) -> list[HackathonEvent]:
        all_events: list[HackathonEvent] = []
        seen_urls: set[str] = set()

        for url in HACKATHON_COM_URLS:
            response = safe_get(url)
            if response is None:
                continue
            events = self._parse_html(response.text, seen_urls)
            all_events.extend(events)

        logger.info("Hackathon.com: trovati %d eventi", len(all_events))
        return all_events

    def _parse_html(self, html: str, seen_urls: set[str]) -> list[HackathonEvent]:
        """Parsa la pagina listing di hackathon.com."""
        soup = BeautifulSoup(html, "lxml")
        events: list[HackathonEvent] = []

        # hackathon.com usa card con link + titolo + date + location
        cards = soup.find_all("div", class_=lambda c: c and "hackathon" in str(c).lower())
        if not cards:
            cards = soup.find_all("a", class_=lambda c: c and ("card" in str(c).lower() or "event" in str(c).lower()))
        if not cards:
            cards = soup.find_all("article")

        for card in cards:
            event = self._parse_card(card, seen_urls)
            if event:
                events.append(event)

        # Fallback generico: cerca tutti i link con /hackathon/ nel path
        if not events:
            links = soup.find_all("a", href=lambda h: h and "/hackathon/" in h)
            for link in links:
                url = link.get("href", "").strip()
                title = link.get_text(strip=True)
                if not url or not title or len(title) < 5 or url in seen_urls:
                    continue
                if not url.startswith("http"):
                    url = f"https://www.hackathon.com{url}"
                seen_urls.add(url)

                events.append(HackathonEvent(
                    title=title,
                    url=url,
                    source=self.name,
                    location="Milano",
                ))

        return events

    def _parse_card(self, card, seen_urls: set[str]) -> HackathonEvent | None:
        """Estrae un evento da una card di hackathon.com."""
        try:
            link = card.find("a") if card.name != "a" else card
            if not link:
                return None

            url = link.get("href", "").strip()
            if not url:
                return None
            if not url.startswith("http"):
                url = f"https://www.hackathon.com{url}"
            if url in seen_urls:
                return None
            seen_urls.add(url)

            # Titolo
            title_el = card.find(["h2", "h3", "h4", "h5"])
            title = title_el.get_text(strip=True) if title_el else link.get_text(strip=True)
            if not title or len(title) < 3:
                return None

            # Data
            date_el = card.find(class_=lambda c: c and ("date" in str(c).lower() or "time" in str(c).lower()))
            date_str = date_el.get_text(strip=True) if date_el else ""

            # Location
            loc_el = card.find(class_=lambda c: c and ("location" in str(c).lower() or "place" in str(c).lower() or "city" in str(c).lower()))
            location = loc_el.get_text(strip=True) if loc_el else "Milano"

            # Description
            desc_el = card.find(class_=lambda c: c and ("desc" in str(c).lower() or "summary" in str(c).lower()))
            description = desc_el.get_text(strip=True)[:500] if desc_el else ""

            return HackathonEvent(
                title=title,
                url=url,
                source=self.name,
                description=description,
                date_str=date_str,
                location=location,
            )
        except Exception as e:
            logger.debug("Hackathon.com parse error: %s", e)
            return None
