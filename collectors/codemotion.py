"""Read Codemotion's public, server-rendered event catalogue."""

import logging
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from models import BaseCollector, HackathonEvent
from utils.collector_health import record_issue
from utils.http import safe_get

logger = logging.getLogger(__name__)

CODEMOTION_URLS = ["https://events.codemotion.com/"]


class CodemotionCollector(BaseCollector):
    @property
    def name(self) -> str:
        return "codemotion"

    def collect(self) -> list[HackathonEvent]:
        events: list[HackathonEvent] = []
        seen: set[str] = set()
        for url in CODEMOTION_URLS:
            response = safe_get(url)
            if response is not None:
                events.extend(self._parse_html(response.text, url, seen))
        logger.info("Codemotion: trovati %d eventi", len(events))
        return events

    def _parse_html(self, html: str, base_url: str, seen_urls: set[str]) -> list[HackathonEvent]:
        soup = BeautifulSoup(html, "lxml")
        cards = soup.select("a.v-card[href]")
        if not cards:
            # An explicit empty catalogue is different from a changed page or JS shell.
            if "there are no events that match" not in soup.get_text(" ", strip=True).lower():
                record_issue("parse_error", "Codemotion event cards not found", base_url)
            return []
        events = []
        for card in cards:
            event = self._parse_card(card, base_url, seen_urls)
            if event:
                events.append(event)
        return events

    def _parse_card(self, card, base_url: str, seen_urls: set[str]) -> HackathonEvent | None:
        title_el = card.select_one(".event-desc h2")
        if title_el is None:
            return None
        title = title_el.get_text(" ", strip=True)
        url = urljoin(base_url, card.get("href", ""))
        parts = urlparse(url)
        host = parts.hostname or ""
        if (len(title) < 5 or url in seen_urls or not card.get("href")
                or parts.scheme not in {"http", "https"}
                or not (host == "codemotion.com" or host.endswith(".codemotion.com"))):
            return None
        date_el = card.select_one(".event-calendar")
        date = date_el.get_text(" ", strip=True) if date_el else ""
        # Most upcoming cards omit the year. Preserve that label as evidence,
        # but never manufacture a year (especially across December/January).
        dated = bool(re.search(r"\b20\d{2}\b", date))
        location_el = card.select_one(".event-topics > span")
        location = location_el.get_text(" ", strip=True).strip(" •") if location_el else ""
        organizer_el = card.select_one(".event-organizer")
        organizer = organizer_el.get_text(" ", strip=True) if organizer_el else "Codemotion"
        type_el = card.select_one(".event-type")
        event_type = type_el.get_text(" ", strip=True) if type_el else ""
        seen_urls.add(url)
        return HackathonEvent(
            title=title, url=url, source=self.name,
            description=". ".join(x for x in [event_type, f"Data indicata: {date}" if date else ""] if x),
            date_str=date if dated else "", date_source="event_card" if dated else "unknown",
            location=location, organizer=organizer,
        )
