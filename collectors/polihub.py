"""Read the official PoliHub event-news archive; report blocked or changed pages."""

import logging
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from models import BaseCollector, HackathonEvent
from utils.collector_health import record_issue
from utils.http import safe_get

logger = logging.getLogger(__name__)

# The current homepage links this archive; the former calendar is retired.
POLIHUB_URLS = ["https://polihub.it/category/eventi/"]


class PoliHubCollector(BaseCollector):
    @property
    def name(self) -> str:
        return "polihub"

    def collect(self) -> list[HackathonEvent]:
        events: list[HackathonEvent] = []
        seen: set[str] = set()
        for url in POLIHUB_URLS:
            response = safe_get(url)
            if response is not None:
                events.extend(self._parse_html(response.text, url, seen))
        logger.info("PoliHub: trovati %d annunci", len(events))
        return events

    def _parse_html(self, html: str, base_url: str, seen_urls: set[str]) -> list[HackathonEvent]:
        soup = BeautifulSoup(html, "lxml")
        events = []
        for card in soup.select("article"):
            event = self._parse_container(card, base_url, seen_urls)
            if event:
                events.append(event)
        if not events and not seen_urls:
            text = soup.get_text(" ", strip=True).lower()
            if not any(marker in text for marker in ("nothing found", "nessun risultato")):
                record_issue("parse_error", "PoliHub article records not found", base_url)
        return events

    def _parse_container(self, container, base_url: str, seen_urls: set[str]) -> HackathonEvent | None:
        title_el = container.find(["h2", "h3", "h4"])
        if title_el is None:
            return None
        link = title_el.find("a", href=True)
        if link is None:
            return None
        title = title_el.get_text(" ", strip=True)
        url = urljoin(base_url, link["href"])
        parts = urlparse(url)
        if (len(title) < 5 or url in seen_urls or parts.scheme not in {"http", "https"}
                or parts.hostname not in {"polihub.it", "www.polihub.it"}
                or parts.path.rstrip("/") in {"", "/eventi", "/en/events"}
                or any(parts.path.startswith(prefix) for prefix in ("/category/", "/tag/", "/author/"))):
            return None
        date_el = container.select_one("time, .meta-date, .date")
        publication = (date_el.get("datetime") or date_el.get_text(" ", strip=True)) if date_el else ""
        desc_el = container.select_one(".excerpt, p")
        seen_urls.add(url)
        return HackathonEvent(
            title=title, url=url, source=self.name,
            description=desc_el.get_text(" ", strip=True)[:500] if desc_el else "",
            date_str="", published_at=publication, date_source="publication",
            location="", organizer="PoliHub",
        )
