"""
Collector Devpost — scraping pagina hackathon upcoming.

URL: https://devpost.com/hackathons?search=milan&status=upcoming
Copertura bassa per Milano ma costo implementativo minimo.
HTML relativamente semplice con card per ogni hackathon.
"""

import logging

from bs4 import BeautifulSoup

import config
from models import BaseCollector, HackathonEvent
from utils.http import safe_get

logger = logging.getLogger(__name__)

DEVPOST_URLS = [
    "https://devpost.com/hackathons?search=milan&status=upcoming",
    "https://devpost.com/hackathons?search=milano&status=upcoming",
    "https://devpost.com/hackathons?search=milan+italy&status=open",
]


class DevpostCollector(BaseCollector):

    @property
    def name(self) -> str:
        return "devpost"

    def collect(self) -> list[HackathonEvent]:
        all_events: list[HackathonEvent] = []
        seen_urls: set[str] = set()

        for url in DEVPOST_URLS:
            response = safe_get(url)
            if response is None:
                continue

            events = self._parse_html(response.text, seen_urls)
            all_events.extend(events)

        logger.info("Devpost: trovati %d hackathon", len(all_events))
        return all_events

    def _parse_html(self, html: str, seen_urls: set[str]) -> list[HackathonEvent]:
        """Parsa la pagina listing di Devpost."""
        soup = BeautifulSoup(html, "lxml")
        events: list[HackathonEvent] = []

        # Devpost usa div.hackathon-tile o simili per ogni hackathon
        tiles = soup.find_all("a", class_=lambda c: c and "hackathon" in str(c).lower())
        if not tiles:
            # Fallback: cerca le card/link principali
            tiles = soup.find_all("div", class_=lambda c: c and ("challenge" in str(c).lower() or "tile" in str(c).lower()))

        # Un altro pattern: Devpost mostra hackathon come link con titolo e info
        if not tiles:
            tiles = soup.select(".hackathons-container a, .challenge-listing a")

        for tile in tiles:
            event = self._parse_tile(tile, seen_urls)
            if event:
                events.append(event)

        # Fallback generico se nessun tile matchato
        if not events:
            events = self._fallback_extraction(soup, seen_urls)

        return events

    def _parse_tile(self, tile, seen_urls: set[str]) -> HackathonEvent | None:
        """Estrae un evento da un tile Devpost."""
        try:
            # URL
            if tile.name == "a":
                url = tile.get("href", "")
            else:
                link = tile.find("a")
                url = link.get("href", "") if link else ""

            if not url:
                return None
            if not url.startswith("http"):
                url = f"https://devpost.com{url}"
            if url in seen_urls:
                return None
            seen_urls.add(url)

            # Titolo
            title_el = tile.find(["h2", "h3", "h4", "h5"])
            if title_el:
                title = title_el.get_text(strip=True)
            else:
                title = tile.get_text(strip=True)[:100]

            if not title or len(title) < 3:
                return None

            # Descrizione e data
            description = ""
            date_str = ""
            for p in tile.find_all("p"):
                text = p.get_text(strip=True)
                if text:
                    description += text + " "

            # Cerca date
            date_el = tile.find(class_=lambda c: c and "date" in str(c).lower())
            if date_el:
                date_str = date_el.get_text(strip=True)

            return HackathonEvent(
                title=title,
                url=url,
                source=self.name,
                description=description.strip()[:500],
                date_str=date_str,
            )

        except Exception as e:
            logger.debug("Errore parsing tile Devpost: %s", e)
            return None

    def _fallback_extraction(self, soup: BeautifulSoup, seen_urls: set[str]) -> list[HackathonEvent]:
        """Fallback: estrae dai link che puntano a hackathon Devpost."""
        events: list[HackathonEvent] = []

        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            text = link.get_text(strip=True)

            if not text or len(text) < 5:
                continue

            # Link a pagine hackathon specifiche
            if "/hackathons/" in href or "devpost.com/hackathons" in href:
                if href.startswith("/"):
                    href = f"https://devpost.com{href}"
                if href in seen_urls or href in [u.split("?")[0] for u in DEVPOST_URLS]:
                    continue
                seen_urls.add(href)

                events.append(HackathonEvent(
                    title=text,
                    url=href,
                    source=self.name,
                ))

        return events


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    collector = DevpostCollector()
    events = collector.collect()
    for e in events:
        print(f"  [{e.source}] {e.title} — {e.url}")
