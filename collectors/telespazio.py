"""Collector Telespazio - scraping pagine Careers/News.

Obiettivo: ridurre il rischio di perdere hackathon pubblicati su
https://www.telespazio.com anche quando non emergono bene via web search.
"""

import logging
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from models import BaseCollector, HackathonEvent
from utils.http import safe_get

logger = logging.getLogger(__name__)

TELESPAZIO_INDEX_URLS = [
    "https://www.telespazio.com/en/careers",
    "https://www.telespazio.com/en/news-and-stories",
    "https://www.telespazio.com/it/news-and-stories",
]

_DETAIL_KEYWORDS = (
    "hackathon",
    "makeathon",
    "datathon",
    "code jam",
    "coding challenge",
    "innovation challenge",
)

_MONTHS = (
    "january|february|march|april|may|june|july|august|september|"
    "october|november|december|"
    "gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|"
    "settembre|ottobre|novembre|dicembre"
)
_DATE_PATTERN = re.compile(
    rf"\b\d{{1,2}}(?:\s*[-/]\s*\d{{1,2}})?\s+(?:{_MONTHS})\s+20\d{{2}}\b",
    re.I,
)


class TelespazioCollector(BaseCollector):

    @property
    def name(self) -> str:
        return "telespazio"

    def collect(self) -> list[HackathonEvent]:
        detail_urls: set[str] = set()

        for index_url in TELESPAZIO_INDEX_URLS:
            response = safe_get(index_url)
            if response is None:
                continue
            detail_urls.update(self._extract_detail_urls(response.text, index_url))

        events: list[HackathonEvent] = []
        for url in sorted(detail_urls):
            event = self._collect_detail(url)
            if event:
                events.append(event)

        logger.info("Telespazio: trovati %d eventi", len(events))
        return events

    def _extract_detail_urls(self, html: str, base_url: str) -> set[str]:
        """Estrae URL plausibili di pagine hackathon da una pagina indice."""
        soup = BeautifulSoup(html, "lxml")
        urls: set[str] = set()

        for a in soup.find_all("a", href=True):
            href = a.get("href", "").strip()
            if not href:
                continue

            abs_url = urljoin(base_url, href)
            parsed = urlparse(abs_url)
            if "telespazio.com" not in parsed.netloc.lower():
                continue

            text = a.get_text(" ", strip=True).lower()
            url_l = abs_url.lower()
            hay = f"{text} {url_l}"

            if any(k in hay for k in _DETAIL_KEYWORDS):
                urls.add(abs_url)

        return urls

    def _collect_detail(self, url: str) -> HackathonEvent | None:
        """Raccoglie titolo/descrizione da una pagina dettaglio."""
        response = safe_get(url)
        if response is None:
            return None

        soup = BeautifulSoup(response.text, "lxml")

        title = self._extract_title(soup)
        if not title:
            return None

        description = self._extract_description(soup)
        full_text = " ".join(soup.stripped_strings)
        loc = "Milano" if re.search(r"\bmilan(?:o)?\b", full_text, re.I) else ""

        date_match = _DATE_PATTERN.search(full_text)
        date_str = date_match.group(0) if date_match else ""

        return HackathonEvent(
            title=title,
            url=url,
            source=self.name,
            description=description,
            date_str=date_str,
            location=loc,
            organizer="Telespazio",
        )

    @staticmethod
    def _extract_title(soup: BeautifulSoup) -> str:
        og_title = soup.find("meta", attrs={"property": "og:title"})
        if og_title and og_title.get("content"):
            return og_title.get("content", "").strip()

        h1 = soup.find("h1")
        if h1:
            return h1.get_text(" ", strip=True)

        if soup.title:
            return soup.title.get_text(" ", strip=True)

        return ""

    @staticmethod
    def _extract_description(soup: BeautifulSoup) -> str:
        og_desc = soup.find("meta", attrs={"property": "og:description"})
        if og_desc and og_desc.get("content"):
            return og_desc.get("content", "").strip()[:500]

        desc = soup.find("meta", attrs={"name": "description"})
        if desc and desc.get("content"):
            return desc.get("content", "").strip()[:500]

        p = soup.find("p")
        if p:
            return p.get_text(" ", strip=True)[:500]

        return ""
