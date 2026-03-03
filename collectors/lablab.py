"""
Collector Lablab.ai — scraping pagina eventi hackathon AI.

Lablab.ai organizza hackathon AI, molti con track Milano/remoto-EU.
URL: https://lablab.ai/event
"""

import json
import logging

from bs4 import BeautifulSoup

import config
from models import BaseCollector, HackathonEvent
from utils.http import safe_get

logger = logging.getLogger(__name__)

LABLAB_URL = "https://lablab.ai/event"

ITALY_KEYWORDS = {"italy", "italia", "milan", "milano", "europe", "europa"}


class LablabCollector(BaseCollector):

    @property
    def name(self) -> str:
        return "lablab"

    def collect(self) -> list[HackathonEvent]:
        response = safe_get(LABLAB_URL)
        if response is None:
            logger.error("Lablab.ai: impossibile raggiungere %s", LABLAB_URL)
            return []

        # Prova __NEXT_DATA__ (Next.js)
        events = self._extract_next_data(response.text)
        if events:
            logger.info("Lablab.ai: trovati %d eventi via __NEXT_DATA__", len(events))
            return events

        # Fallback HTML
        events = self._parse_html(response.text)
        logger.info("Lablab.ai: trovati %d eventi via HTML", len(events))
        return events

    def _extract_next_data(self, html: str) -> list[HackathonEvent]:
        """Estrae eventi da __NEXT_DATA__."""
        soup = BeautifulSoup(html, "lxml")
        script = soup.find("script", id="__NEXT_DATA__")
        if not script:
            return []

        events = []
        seen_urls: set[str] = set()
        try:
            data = json.loads(script.string)
            page_props = data.get("props", {}).get("pageProps", {})
            event_list = page_props.get("events", []) or page_props.get("hackathons", [])

            for item in event_list:
                title = item.get("name", "") or item.get("title", "")
                slug = item.get("slug", "")
                url = f"https://lablab.ai/event/{slug}" if slug else item.get("url", "")
                if not url or not title or url in seen_urls:
                    continue
                seen_urls.add(url)

                # Lablab ha molti hackathon online/globali — li includiamo tutti
                # e lasciamo che il filtro LLM decida se sono rilevanti per Milano
                events.append(HackathonEvent(
                    title=title,
                    url=url,
                    source=self.name,
                    description=(item.get("description", "") or item.get("tagline", "") or "")[:500],
                    date_str=item.get("startDate", "") or item.get("start_date", ""),
                    location=item.get("location", "") or "",
                    organizer="lablab.ai",
                ))
        except (json.JSONDecodeError, KeyError) as e:
            logger.debug("Lablab.ai __NEXT_DATA__ error: %s", e)

        return events

    def _parse_html(self, html: str) -> list[HackathonEvent]:
        """Parsa le card evento dalla pagina HTML."""
        soup = BeautifulSoup(html, "lxml")
        events: list[HackathonEvent] = []
        seen_urls: set[str] = set()

        cards = soup.find_all("div", class_=lambda c: c and ("event" in str(c).lower() or "card" in str(c).lower() or "hackathon" in str(c).lower()))
        if not cards:
            cards = soup.find_all("a", href=lambda h: h and "/event/" in h)

        for card in cards:
            try:
                if card.name == "a":
                    link = card
                else:
                    link = card.find("a", href=True)
                if not link:
                    continue

                url = link.get("href", "").strip()
                if not url.startswith("http"):
                    url = f"https://lablab.ai{url}"
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                title_el = card.find(["h2", "h3", "h4"])
                title = title_el.get_text(strip=True) if title_el else link.get_text(strip=True)
                if not title or len(title) < 3:
                    continue

                date_el = card.find(class_=lambda c: c and "date" in str(c).lower())
                date_str = date_el.get_text(strip=True) if date_el else ""

                events.append(HackathonEvent(
                    title=title,
                    url=url,
                    source=self.name,
                    date_str=date_str,
                    organizer="lablab.ai",
                ))
            except Exception as e:
                logger.debug("Lablab.ai card parse error: %s", e)

        return events
