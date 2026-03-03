"""
Collector MLH (Major League Hacking) — JSON API pubblica.

Endpoint: https://mlh.io/seasons/2026/events
MLH pubblica i dati degli eventi in un endpoint JSON accessibile.
Buona copertura per hackathon universitari EU.
"""

import json
import logging
from datetime import datetime

from bs4 import BeautifulSoup

import config
from models import BaseCollector, HackathonEvent
from utils.http import safe_get, safe_get_json

logger = logging.getLogger(__name__)

# MLH pubblica le stagioni con anno accademico
CURRENT_YEAR = datetime.now().year
MLH_URLS = [
    f"https://mlh.io/seasons/{CURRENT_YEAR}/events",
    f"https://mlh.io/seasons/{CURRENT_YEAR + 1}/events",
]

# Filtro geo: solo eventi in Italia o con Milan/Milano nel nome/location
ITALY_KEYWORDS = {"italy", "italia", "milan", "milano", "rome", "roma", "turin", "torino"}


class MLHCollector(BaseCollector):

    @property
    def name(self) -> str:
        return "mlh"

    def collect(self) -> list[HackathonEvent]:
        all_events: list[HackathonEvent] = []
        seen_urls: set[str] = set()

        for url in MLH_URLS:
            events = self._fetch_season(url, seen_urls)
            all_events.extend(events)

        logger.info("MLH: trovati %d eventi (Italia/Milano)", len(all_events))
        return all_events

    def _fetch_season(self, url: str, seen_urls: set[str]) -> list[HackathonEvent]:
        """Fetch una stagione MLH e filtra per Italia."""
        response = safe_get(url)
        if response is None:
            return []

        # MLH può restituire JSON diretto o HTML con dati embedded
        events: list[HackathonEvent] = []

        # Prova parsing HTML (MLH rende la pagina con card)
        events = self._parse_html(response.text, seen_urls)

        return events

    def _parse_html(self, html: str, seen_urls: set[str]) -> list[HackathonEvent]:
        """Parsa la pagina eventi MLH."""
        soup = BeautifulSoup(html, "lxml")
        events: list[HackathonEvent] = []

        # MLH usa div.event-wrapper o simili per le card
        cards = soup.find_all("div", class_=lambda c: c and "event" in str(c).lower())
        if not cards:
            cards = soup.find_all("article")

        for card in cards:
            event = self._parse_card(card, seen_urls)
            if event:
                events.append(event)

        # Fallback: cerca __NEXT_DATA__ o script JSON
        if not events:
            script = soup.find("script", id="__NEXT_DATA__")
            if script:
                try:
                    data = json.loads(script.string)
                    events = self._extract_from_json(data, seen_urls)
                except (json.JSONDecodeError, KeyError):
                    pass

        return events

    def _parse_card(self, card, seen_urls: set[str]) -> HackathonEvent | None:
        """Estrae un evento da una card MLH, filtra per Italia."""
        try:
            # Location check — solo Italia
            loc_el = card.find(class_=lambda c: c and ("location" in str(c).lower() or "city" in str(c).lower()))
            location = loc_el.get_text(strip=True) if loc_el else ""

            # Titolo
            title_el = card.find(["h3", "h4", "h2", "h5"])
            title = title_el.get_text(strip=True) if title_el else ""

            # Filtro geografico: solo Italia/Milano
            text_to_check = f"{title} {location}".lower()
            if not any(kw in text_to_check for kw in ITALY_KEYWORDS):
                return None

            # URL
            link = card.find("a", href=True)
            if not link:
                return None
            url = link.get("href", "").strip()
            if not url.startswith("http"):
                url = f"https://mlh.io{url}"
            if url in seen_urls:
                return None
            seen_urls.add(url)

            if not title:
                title = link.get_text(strip=True)
            if not title:
                return None

            # Data
            date_el = card.find(class_=lambda c: c and "date" in str(c).lower())
            date_str = date_el.get_text(strip=True) if date_el else ""

            return HackathonEvent(
                title=title,
                url=url,
                source=self.name,
                date_str=date_str,
                location=location or "Italia",
                organizer="Major League Hacking",
            )
        except Exception as e:
            logger.debug("MLH card parse error: %s", e)
            return None

    def _extract_from_json(self, data: dict, seen_urls: set[str]) -> list[HackathonEvent]:
        """Estrae eventi da __NEXT_DATA__ JSON."""
        events = []
        try:
            # Navigate the JSON structure to find events
            page_props = data.get("props", {}).get("pageProps", {})
            event_list = page_props.get("events", [])

            for item in event_list:
                location = item.get("location", "")
                title = item.get("name", "") or item.get("title", "")
                text_to_check = f"{title} {location}".lower()

                if not any(kw in text_to_check for kw in ITALY_KEYWORDS):
                    continue

                url = item.get("url", "") or item.get("link", "")
                if not url or url in seen_urls:
                    continue
                if not url.startswith("http"):
                    url = f"https://mlh.io{url}"
                seen_urls.add(url)

                events.append(HackathonEvent(
                    title=title,
                    url=url,
                    source=self.name,
                    description=(item.get("description", "") or "")[:500],
                    date_str=item.get("startDate", "") or item.get("date", ""),
                    location=location or "Italia",
                    organizer="Major League Hacking",
                ))
        except Exception as e:
            logger.debug("MLH JSON extraction error: %s", e)

        return events
