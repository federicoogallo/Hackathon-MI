"""
Collector Camera di Commercio Milano — scraping pagina eventi/bandi.

Recupera eventi e bandi con componente hackathon dalla Camera di
Commercio di Milano Monza Brianza Lodi.
URL: https://www.milomb.camcom.it
"""

import logging

from bs4 import BeautifulSoup

import config
from models import BaseCollector, HackathonEvent
from utils.http import safe_get

logger = logging.getLogger(__name__)

CAMERA_COMMERCIO_URLS = [
    "https://www.milomb.camcom.it/eventi",
    "https://www.milomb.camcom.it/bandi-e-contributi",
]


class CameraCommercioCollector(BaseCollector):

    @property
    def name(self) -> str:
        return "camera_commercio"

    def collect(self) -> list[HackathonEvent]:
        all_events: list[HackathonEvent] = []
        seen_urls: set[str] = set()

        for url in CAMERA_COMMERCIO_URLS:
            response = safe_get(url)
            if response is None:
                continue
            events = self._parse_html(response.text, url, seen_urls)
            all_events.extend(events)

        logger.info("Camera Commercio: trovati %d eventi", len(all_events))
        return all_events

    def _parse_html(self, html: str, base_url: str, seen_urls: set[str]) -> list[HackathonEvent]:
        """Parsa le pagine della Camera di Commercio."""
        soup = BeautifulSoup(html, "lxml")
        events: list[HackathonEvent] = []

        cards = soup.find_all("article")
        if not cards:
            cards = soup.find_all("div", class_=lambda c: c and ("event" in str(c).lower() or "item" in str(c).lower() or "card" in str(c).lower() or "news" in str(c).lower()))
        if not cards:
            cards = soup.find_all("li", class_=lambda c: c and "item" in str(c).lower())

        for card in cards:
            link = card.find("a", href=True)
            if not link:
                continue

            url = link.get("href", "").strip()
            title_el = card.find(["h2", "h3", "h4"])
            title = title_el.get_text(strip=True) if title_el else link.get_text(strip=True)

            if not url or not title or len(title) < 5 or url in seen_urls:
                continue
            if not url.startswith("http"):
                from urllib.parse import urljoin
                url = urljoin(base_url, url)
            seen_urls.add(url)

            date_el = card.find(["time"]) or card.find(class_=lambda c: c and "date" in str(c).lower())
            date_str = ""
            if date_el:
                date_str = date_el.get("datetime", "") or date_el.get_text(strip=True)

            desc_el = card.find(class_=lambda c: c and ("desc" in str(c).lower() or "text" in str(c).lower()))
            description = desc_el.get_text(strip=True)[:500] if desc_el else ""

            events.append(HackathonEvent(
                title=title,
                url=url,
                source=self.name,
                description=description,
                date_str=date_str,
                location="Milano",
                organizer="Camera di Commercio Milano",
            ))

        return events
