"""
Collector Devfolio — estrazione eventi da devfolio.co.

Devfolio è una piattaforma crescente in EU per hackathon.
Usa Next.js, quindi si può estrarre da __NEXT_DATA__ (come Luma).
"""

import json
import logging

from bs4 import BeautifulSoup

import config
from models import BaseCollector, HackathonEvent
from utils.http import safe_get

logger = logging.getLogger(__name__)

DEVFOLIO_URLS = [
    "https://devfolio.co/hackathons",
    "https://devfolio.co/hackathons?type=upcoming",
]

ITALY_KEYWORDS = {"italy", "italia", "milan", "milano", "europe", "europa"}


class DevfolioCollector(BaseCollector):

    @property
    def name(self) -> str:
        return "devfolio"

    def collect(self) -> list[HackathonEvent]:
        all_events: list[HackathonEvent] = []
        seen_urls: set[str] = set()

        for url in DEVFOLIO_URLS:
            response = safe_get(url)
            if response is None:
                continue

            # Try __NEXT_DATA__ first
            events = self._extract_next_data(response.text, seen_urls)
            if events:
                all_events.extend(events)
                continue

            # Fallback: HTML scraping
            events = self._parse_html(response.text, seen_urls)
            all_events.extend(events)

        logger.info("Devfolio: trovati %d eventi", len(all_events))
        return all_events

    def _extract_next_data(self, html: str, seen_urls: set[str]) -> list[HackathonEvent]:
        """Estrae dati dal tag __NEXT_DATA__."""
        soup = BeautifulSoup(html, "lxml")
        script = soup.find("script", id="__NEXT_DATA__")
        if not script:
            return []

        events = []
        try:
            data = json.loads(script.string)
            hackathons = (
                data.get("props", {})
                .get("pageProps", {})
                .get("hackathons", [])
            )
            if not hackathons:
                # Try alternative paths
                hackathons = (
                    data.get("props", {})
                    .get("pageProps", {})
                    .get("initialData", {})
                    .get("hackathons", [])
                )

            for h in hackathons:
                title = h.get("name", "") or h.get("title", "")
                location = h.get("location", "") or h.get("city", "")
                desc = h.get("description", "") or h.get("tagline", "")

                # Filtro geo
                text_to_check = f"{title} {location} {desc}".lower()
                if not any(kw in text_to_check for kw in ITALY_KEYWORDS):
                    continue

                slug = h.get("slug", "")
                url = h.get("url", "")
                if not url and slug:
                    url = f"https://devfolio.co/hackathons/{slug}"
                if not url:
                    continue
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                events.append(HackathonEvent(
                    title=title,
                    url=url,
                    source=self.name,
                    description=(desc or "")[:500],
                    date_str=h.get("starts_at", "") or h.get("startDate", ""),
                    location=location or "",
                    organizer=h.get("organizer_name", ""),
                ))
        except (json.JSONDecodeError, KeyError) as e:
            logger.debug("Devfolio __NEXT_DATA__ error: %s", e)

        return events

    def _parse_html(self, html: str, seen_urls: set[str]) -> list[HackathonEvent]:
        """Parsa le card hackathon dalla pagina HTML."""
        soup = BeautifulSoup(html, "lxml")
        events = []

        cards = soup.find_all("div", class_=lambda c: c and ("hackathon" in str(c).lower() or "card" in str(c).lower()))
        if not cards:
            cards = soup.find_all("a", href=lambda h: h and "/hackathons/" in h)

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
                    url = f"https://devfolio.co{url}"
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                title_el = card.find(["h2", "h3", "h4"])
                title = title_el.get_text(strip=True) if title_el else link.get_text(strip=True)
                if not title or len(title) < 3:
                    continue

                events.append(HackathonEvent(
                    title=title,
                    url=url,
                    source=self.name,
                ))
            except Exception as e:
                logger.debug("Devfolio card parse error: %s", e)

        return events
