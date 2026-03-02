"""
Collector PoliHub — scraping pagina eventi dell'incubatore del Politecnico di Milano.

URL: https://www.polihub.it/it/eventi/ (e versione inglese)
Eventi spesso vuoti, ma quando presenti sono di alta qualità (hackathon accademici).
"""

import logging

from bs4 import BeautifulSoup

import config
from models import BaseCollector, HackathonEvent
from utils.http import safe_get

logger = logging.getLogger(__name__)

POLIHUB_URLS = [
    "https://polihub.it/eventi/",
    "https://polihub.it/en/events/",
]


class PoliHubCollector(BaseCollector):

    @property
    def name(self) -> str:
        return "polihub"

    def collect(self) -> list[HackathonEvent]:
        all_events: list[HackathonEvent] = []
        seen_urls: set[str] = set()

        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "it-IT,it;q=0.9,en;q=0.7",
            "Referer": "https://www.google.com/",
        }

        for url in POLIHUB_URLS:
            response = safe_get(url, headers=headers)
            if response is None:
                continue

            events = self._parse_html(response.text, url, seen_urls)
            all_events.extend(events)

        logger.info("PoliHub: trovati %d eventi", len(all_events))
        return all_events

    def _parse_html(self, html: str, base_url: str, seen_urls: set[str]) -> list[HackathonEvent]:
        """Parsa la pagina eventi di PoliHub."""
        soup = BeautifulSoup(html, "lxml")
        events: list[HackathonEvent] = []

        # PoliHub tipicamente mostra card con eventi
        # Cerca article, div con classi event/card, o sezioni con link
        containers = soup.find_all("article")
        if not containers:
            containers = soup.find_all(
                "div",
                class_=lambda c: c and any(
                    k in str(c).lower() for k in ("event", "card", "post", "item")
                ),
            )

        for container in containers:
            event = self._parse_container(container, base_url, seen_urls)
            if event:
                events.append(event)

        # Fallback: link extraction
        if not events:
            for link in soup.find_all("a", href=True):
                href = link.get("href", "")
                text = link.get_text(strip=True)
                if text and len(text) > 5 and "/event" in href.lower():
                    if href.startswith("/"):
                        href = f"https://polihub.it{href}"
                    if href not in seen_urls and href not in [u for u in POLIHUB_URLS]:
                        seen_urls.add(href)
                        events.append(HackathonEvent(
                            title=text, url=href, source=self.name,
                            location=config.SEARCH_LOCATION,
                        ))

        return events

    def _parse_container(self, container, base_url: str, seen_urls: set[str]) -> HackathonEvent | None:
        """Estrae un evento da un container HTML."""
        try:
            title_el = container.find(["h2", "h3", "h4"])
            if not title_el:
                return None

            title = title_el.get_text(strip=True)
            if not title:
                return None

            link = container.find("a", href=True)
            url = link.get("href", "") if link else ""
            if url.startswith("/"):
                url = f"https://polihub.it{url}"
            if not url or url in seen_urls:
                return None
            seen_urls.add(url)

            # Data
            date_str = ""
            time_el = container.find("time")
            if time_el:
                date_str = time_el.get("datetime", "") or time_el.get_text(strip=True)

            # Descrizione
            desc_el = container.find("p")
            description = desc_el.get_text(strip=True)[:500] if desc_el else ""

            return HackathonEvent(
                title=title,
                url=url,
                source=self.name,
                description=description,
                date_str=date_str,
                location=config.SEARCH_LOCATION,
                organizer="PoliHub",
            )

        except Exception as e:
            logger.debug("Errore parsing container PoliHub: %s", e)
            return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    collector = PoliHubCollector()
    events = collector.collect()
    for e in events:
        print(f"  [{e.source}] {e.title} — {e.url}")
