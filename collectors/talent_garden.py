"""
Collector Talent Garden — scraping eventi dal sito ufficiale.

Talent Garden ha sedi a Milano (Calabiana, Isola) e organizza
hackathon frequenti. Scraping della pagina eventi Italia.
"""

import logging
import json
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from models import BaseCollector, HackathonEvent
from utils.http import safe_get

logger = logging.getLogger(__name__)

TALENT_GARDEN_URLS = [
    "https://talentgarden.com/it/agenda",
]


class TalentGardenCollector(BaseCollector):

    @property
    def name(self) -> str:
        return "talent_garden"

    def collect(self) -> list[HackathonEvent]:
        all_events: list[HackathonEvent] = []
        seen_urls: set[str] = set()

        for url in TALENT_GARDEN_URLS:
            response = safe_get(url)
            if response is None:
                continue
            events = self._parse_html(response.text, url, seen_urls)
            all_events.extend(events)

        logger.info("Talent Garden: trovati %d eventi", len(all_events))
        return all_events

    def _parse_html(self, html: str, base_url: str, seen_urls: set[str]) -> list[HackathonEvent]:
        """Parsa la pagina eventi di Talent Garden."""
        soup = BeautifulSoup(html, "lxml")
        events = self._parse_agenda_data(soup, seen_urls)
        if events:
            return events

        # Talent Garden usa card per gli eventi
        cards = soup.find_all("div", class_=lambda c: c and ("event" in str(c).lower() or "card" in str(c).lower()))
        if not cards:
            cards = soup.find_all("article")

        for card in cards:
            event = self._parse_card(card, base_url, seen_urls)
            if event:
                events.append(event)

        # Fallback: link a eventi
        if not events:
            links = soup.find_all("a", href=lambda h: h and ("event" in h.lower() or "hackathon" in h.lower()))
            for link in links:
                href = link.get("href", "").strip()
                title = link.get_text(strip=True)
                if not href or not title or len(title) < 5 or href in seen_urls:
                    continue
                if not href.startswith("http"):
                    from urllib.parse import urljoin
                    href = urljoin(base_url, href)
                seen_urls.add(href)

                events.append(HackathonEvent(
                    title=title,
                    url=href,
                    source=self.name,
                    location="",
                    organizer="Talent Garden",
                ))

        return events

    def _parse_agenda_data(self, soup: BeautifulSoup, seen_urls: set[str]) -> list[HackathonEvent]:
        """Read the public agenda's event data without executing its client JavaScript."""
        events: list[HackathonEvent] = []
        decoder = json.JSONDecoder()
        for script in soup.find_all("script"):
            text = script.string or script.get_text()
            for match in re.finditer(r"\bvar\s+newIslands\s*=\s*", text):
                try:
                    islands, _ = decoder.raw_decode(text, match.end())
                except (ValueError, RecursionError):
                    continue
                if not isinstance(islands, list):
                    continue
                for island in islands:
                    if not isinstance(island, dict) or island.get("moduleName") != "Slider":
                        continue
                    props = island.get("props", {})
                    if not isinstance(props, dict) or props.get("variant") != "variant-events":
                        continue
                    rows = props.get("data", [])
                    if not isinstance(rows, list):
                        continue
                    for row in rows:
                        if not isinstance(row, dict):
                            continue
                        title, url = row.get("event_name"), row.get("url")
                        if not isinstance(title, str) or not title.strip() or not isinstance(url, str):
                            continue
                        if urlparse(url).scheme not in {"http", "https"} or url in seen_urls:
                            continue
                        if row.get("status") in {"draft", "canceled", "cancelled", "deleted"}:
                            continue
                        seen_urls.add(url)
                        venue = row.get("venue_info", {})
                        location = venue.get("localized_address_display", "") if isinstance(venue, dict) else ""
                        location = location if isinstance(location, str) else ""
                        if row.get("online_event") is True:
                            location = "Online"
                        start, end = row.get("start_utc"), row.get("end_utc")
                        date_str = start if isinstance(start, str) else ""
                        if date_str and isinstance(end, str) and end:
                            date_str += f" — {end}"
                        description = row.get("description") or row.get("summary") or ""
                        description = BeautifulSoup(description, "lxml").get_text(" ", strip=True)[:1800] if isinstance(description, str) else ""
                        organizer = row.get("organizer_name")
                        events.append(HackathonEvent(
                            title=title.strip(), url=url, source=self.name,
                            description=description, date_str=date_str,
                            date_source="event_api" if date_str else "unknown",
                            location=location,
                            organizer=organizer if isinstance(organizer, str) else "Talent Garden",
                        ))
        return events

    def _parse_card(self, card, base_url: str, seen_urls: set[str]) -> HackathonEvent | None:
        """Estrae un evento da una card Talent Garden."""
        try:
            link = card.find("a", href=True)
            if not link:
                return None

            url = link.get("href", "").strip()
            if not url:
                return None
            if not url.startswith("http"):
                url = urljoin(base_url, url)
            if url in seen_urls:
                return None
            seen_urls.add(url)

            # Titolo
            title_el = card.find(["h2", "h3", "h4", "h5"])
            title = title_el.get_text(strip=True) if title_el else link.get_text(strip=True)
            if not title or len(title) < 3:
                return None

            # Data
            date_el = card.find(["time"]) or card.find(class_=lambda c: c and "date" in str(c).lower())
            date_str = ""
            if date_el:
                date_str = date_el.get("datetime", "") or date_el.get_text(strip=True)

            # Location
            loc_el = card.find(class_=lambda c: c and ("location" in str(c).lower() or "venue" in str(c).lower() or "campus" in str(c).lower()))
            location = loc_el.get_text(strip=True) if loc_el else ""

            # Description
            desc_el = card.find(class_=lambda c: c and ("desc" in str(c).lower() or "excerpt" in str(c).lower()))
            description = desc_el.get_text(strip=True)[:500] if desc_el else ""

            return HackathonEvent(
                title=title,
                url=url,
                source=self.name,
                description=description,
                date_str=date_str,
                date_source="event_card" if date_str else "unknown",
                location=location,
                organizer="Talent Garden",
            )
        except Exception as e:
            logger.debug("Talent Garden card parse error: %s", e)
            return None
