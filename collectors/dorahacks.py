"""
Collector DoraHacks — REST API pubblica.

DoraHacks è una piattaforma per hackathon web3/blockchain con
un'API REST pubblica. Filtra per eventi in Italia/Milano.
"""

import logging

import config
from models import BaseCollector, HackathonEvent
from utils.http import safe_get_json

logger = logging.getLogger(__name__)

DORAHACKS_API_URL = "https://dorahacks.io/api/hackathon/list"

ITALY_KEYWORDS = {"italy", "italia", "milan", "milano", "europe", "europa"}


class DoraHacksCollector(BaseCollector):

    @property
    def name(self) -> str:
        return "dorahacks"

    def collect(self) -> list[HackathonEvent]:
        all_events: list[HackathonEvent] = []
        seen_urls: set[str] = set()

        # Fetch paginated results
        for page in range(1, 4):  # Max 3 pagine
            params = {
                "page": page,
                "page_size": 50,
                "status": "active",
            }
            data = safe_get_json(DORAHACKS_API_URL, params=params)
            if not data:
                break

            results = data if isinstance(data, list) else data.get("results", data.get("data", []))
            if not isinstance(results, list) or not results:
                break

            for item in results:
                event = self._parse_item(item, seen_urls)
                if event:
                    all_events.append(event)

        logger.info("DoraHacks: trovati %d eventi (Italia/Milano)", len(all_events))
        return all_events

    def _parse_item(self, item: dict, seen_urls: set[str]) -> HackathonEvent | None:
        """Parsa un hackathon dal JSON dell'API."""
        try:
            title = item.get("name", "") or item.get("title", "")
            location = item.get("location", "") or item.get("city", "")
            description = item.get("description", "") or item.get("intro", "")

            # Filtro geo: solo Italia/Milano/Europe
            text_to_check = f"{title} {location} {description}".lower()
            if not any(kw in text_to_check for kw in ITALY_KEYWORDS):
                return None

            # URL
            slug = item.get("slug", "") or item.get("id", "")
            url = item.get("url", "") or item.get("link", "")
            if not url and slug:
                url = f"https://dorahacks.io/hackathon/{slug}"
            if not url:
                return None
            if url in seen_urls:
                return None
            seen_urls.add(url)

            if not title:
                return None

            # Date
            date_str = item.get("start_time", "") or item.get("startDate", "") or item.get("start_date", "")

            return HackathonEvent(
                title=title,
                url=url,
                source=self.name,
                description=(description or "")[:500],
                date_str=date_str,
                location=location or "Online/Milano",
                organizer=item.get("organizer", {}).get("name", "") if isinstance(item.get("organizer"), dict) else "",
            )
        except Exception as e:
            logger.debug("DoraHacks parse error: %s", e)
            return None
