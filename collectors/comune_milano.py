"""Collect official municipal announcements from the current news index."""

import logging
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from models import BaseCollector, HackathonEvent
from utils.collector_health import record_issue
from utils.http import safe_get

logger = logging.getLogger(__name__)

COMUNE_URLS = [
    "https://www.comune.milano.it/notizie",
    # Sorting and page size are exposed by the public archive's search form.
    "https://www.comune.milano.it/notizie/comunicati-stampa?sort=modified-&delta=60",
]


class ComuneMilanoCollector(BaseCollector):
    @property
    def name(self) -> str:
        return "comune_milano"

    def collect(self) -> list[HackathonEvent]:
        events: list[HackathonEvent] = []
        seen: set[str] = set()
        for url in COMUNE_URLS:
            response = safe_get(url)
            if response is not None:
                events.extend(self._parse_html(response.text, url, seen))
        logger.info("Comune Milano: trovati %d annunci", len(events))
        return events

    def _parse_html(self, html: str, base_url: str, seen_urls: set[str]) -> list[HackathonEvent]:
        previous_urls = seen_urls
        seen_urls = set()
        soup = BeautifulSoup(html, "lxml")
        events = []
        for card in soup.select("article, .card, li.search-results-item"):
            title_el = card.find(["h2", "h3", "h4"])
            link = title_el.find("a", href=True) if title_el else None
            if link is None:
                link = card.select_one('a[href*="/w/"], a[href*="/-/"]')
            if title_el is None or link is None:
                continue
            title = title_el.get_text(" ", strip=True)
            url = urljoin(base_url, link["href"])
            parts = urlparse(url)
            if (len(title) < 5 or url in seen_urls or parts.scheme not in {"http", "https"}
                    or parts.hostname not in {"www.comune.milano.it", "comune.milano.it"}
                    or not parts.path.startswith(("/w/", "/-/"))):
                continue
            date_el = card.select_one("time, .date, .card-date, .category-top .data")
            publication = (date_el.get("datetime") or date_el.get_text(" ", strip=True)) if date_el else ""
            desc_el = card.select_one(".card-text, .description, .abstract, p")
            seen_urls.add(url)
            events.append(HackathonEvent(
                title=title, url=url, source=self.name,
                description=desc_el.get_text(" ", strip=True)[:500] if desc_el else "",
                date_str="", published_at=publication, date_source="publication",
                location="", organizer="Comune di Milano",
            ))
        if not events and not any(x in soup.get_text(" ", strip=True).lower()
                                  for x in ("nessun risultato", "nessuna notizia")):
            record_issue("parse_error", "Municipal news records not found", base_url)
        unique_events = [event for event in events if event.url not in previous_urls]
        previous_urls.update(event.url for event in events)
        return unique_events
