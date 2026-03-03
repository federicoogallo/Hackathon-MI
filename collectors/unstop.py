"""
Collector Unstop (ex-Dare2Compete) — scraping pagina hackathon.

Piattaforma di hackathon e competition con presenza crescente in EU.
URL: https://unstop.com/hackathons
"""

import logging

from bs4 import BeautifulSoup

import config
from models import BaseCollector, HackathonEvent
from utils.http import safe_get

logger = logging.getLogger(__name__)

UNSTOP_URLS = [
    "https://unstop.com/hackathons?oppstatus=open",
    "https://unstop.com/hackathons?oppstatus=recent",
]


class UnstopCollector(BaseCollector):

    @property
    def name(self) -> str:
        return "unstop"

    def collect(self) -> list[HackathonEvent]:
        all_events: list[HackathonEvent] = []
        seen_urls: set[str] = set()

        for url in UNSTOP_URLS:
            response = safe_get(url)
            if response is None:
                continue
            events = self._parse_html(response.text, seen_urls)
            all_events.extend(events)

        logger.info("Unstop: trovati %d eventi", len(all_events))
        return all_events

    def _parse_html(self, html: str, seen_urls: set[str]) -> list[HackathonEvent]:
        """Parsa la pagina hackathon di Unstop."""
        soup = BeautifulSoup(html, "lxml")
        events: list[HackathonEvent] = []

        cards = soup.find_all("div", class_=lambda c: c and ("card" in str(c).lower() or "hackathon" in str(c).lower() or "listing" in str(c).lower()))
        if not cards:
            cards = soup.find_all("article")
        if not cards:
            # Unstop potrebbe usare Angular e renderizzare lato client
            # In tal caso, cerchiamo script con JSON
            import json
            for script in soup.find_all("script", type="application/json"):
                try:
                    data = json.loads(script.string)
                    events.extend(self._extract_from_json(data, seen_urls))
                except (json.JSONDecodeError, TypeError):
                    continue
            return events

        for card in cards:
            event = self._parse_card(card, seen_urls)
            if event:
                events.append(event)

        return events

    def _parse_card(self, card, seen_urls: set[str]) -> HackathonEvent | None:
        """Estrae un evento da una card Unstop."""
        try:
            link = card.find("a", href=True)
            if not link:
                return None

            url = link.get("href", "").strip()
            if not url:
                return None
            if not url.startswith("http"):
                url = f"https://unstop.com{url}"
            if url in seen_urls:
                return None
            seen_urls.add(url)

            title_el = card.find(["h2", "h3", "h4", "h5"])
            title = title_el.get_text(strip=True) if title_el else link.get_text(strip=True)
            if not title or len(title) < 3:
                return None

            date_el = card.find(class_=lambda c: c and ("date" in str(c).lower() or "deadline" in str(c).lower()))
            date_str = date_el.get_text(strip=True) if date_el else ""

            loc_el = card.find(class_=lambda c: c and "location" in str(c).lower())
            location = loc_el.get_text(strip=True) if loc_el else ""

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
            logger.debug("Unstop card parse error: %s", e)
            return None

    def _extract_from_json(self, data, seen_urls: set[str]) -> list[HackathonEvent]:
        """Estrae eventi da dati JSON embedded nella pagina."""
        events = []
        items = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("hackathons", data.get("data", data.get("results", [])))

        if not isinstance(items, list):
            return events

        for item in items:
            if not isinstance(item, dict):
                continue
            title = item.get("title", "") or item.get("name", "")
            url = item.get("url", "") or item.get("link", "")
            if not title or not url or url in seen_urls:
                continue
            if not url.startswith("http"):
                url = f"https://unstop.com{url}"
            seen_urls.add(url)

            events.append(HackathonEvent(
                title=title,
                url=url,
                source=self.name,
                description=(item.get("description", "") or "")[:500],
                date_str=item.get("start_date", "") or item.get("deadline", ""),
                location=item.get("location", "") or "",
            ))

        return events
