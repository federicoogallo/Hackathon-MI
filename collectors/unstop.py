"""
Collector Unstop (ex-Dare2Compete) — API pubblica del catalogo hackathon.

Piattaforma di hackathon e competition con presenza crescente in EU.
Endpoint usato dal modulo GlobalSearchModule di https://unstop.com/hackathons.
"""

import json
import logging
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from models import BaseCollector, HackathonEvent
from utils.collector_health import record_issue
from utils.http import safe_get

logger = logging.getLogger(__name__)

UNSTOP_API_URL = "https://unstop.com/api/public/opportunity/search-result"
UNSTOP_QUERIES = ("milan", "milano", "italy")


class UnstopCollector(BaseCollector):

    @property
    def name(self) -> str:
        return "unstop"

    def collect(self) -> list[HackathonEvent]:
        all_events: list[HackathonEvent] = []
        seen_urls: set[str] = set()

        for query in UNSTOP_QUERIES:
            for page in range(1, 4):
                response = safe_get(UNSTOP_API_URL, params={
                    "opportunity": "hackathons", "oppstatus": "open",
                    "searchTerm": query, "page": page, "per_page": 20,
                })
                if response is None:
                    break
                try:
                    payload = json.loads(response.text)
                except (ValueError, TypeError):
                    record_issue("parse_error", "invalid public catalogue JSON", UNSTOP_API_URL)
                    break
                listing = payload.get("data") if isinstance(payload, dict) else None
                if not isinstance(listing, dict) or not isinstance(listing.get("data"), list):
                    record_issue("parse_error", "unexpected public catalogue schema", UNSTOP_API_URL)
                    break
                items = listing["data"]
                readable = 0
                for item in items:
                    event = self._parse_api_item(item)
                    if event:
                        readable += 1
                        if self._in_scope(item) and event.url not in seen_urls:
                            seen_urls.add(event.url)
                            all_events.append(event)
                if items and not readable:
                    record_issue("parse_error", "public catalogue has no readable events", UNSTOP_API_URL)
                    break
                last_page = listing.get("last_page")
                if not items or (isinstance(last_page, int) and page >= last_page):
                    break

        logger.info("Unstop: trovati %d eventi", len(all_events))
        return all_events

    def _parse_api_item(self, item) -> HackathonEvent | None:
        if not isinstance(item, dict) or item.get("type") != "hackathons":
            return None
        title = item.get("title")
        url = self._event_url(item.get("public_url"))
        if not isinstance(title, str) or not title.strip() or not url:
            return None
        address = item.get("address_with_country_logo")
        location = ""
        if isinstance(address, dict):
            country = address.get("country")
            parts = [address.get("address"), address.get("city"), address.get("state"),
                     country.get("name") if isinstance(country, dict) else None]
            location = ", ".join(dict.fromkeys(value.strip() for value in parts if isinstance(value, str) and value.strip()))
        if item.get("region") == "online":
            location = "Online"
        organisation = item.get("organisation")
        organiser = organisation.get("name", "") if isinstance(organisation, dict) else ""
        details = item.get("details") if isinstance(item.get("details"), str) else ""
        description = BeautifulSoup(details, "lxml").get_text(" ", strip=True)[:500]
        # The catalogue's end_date can be registration closure, not the event start.
        deadline = item.get("end_date") if isinstance(item.get("end_date"), str) else ""
        return HackathonEvent(
            title=title.strip(), url=url, source=self.name, description=description,
            location=location, organizer=organiser, date_str=deadline,
            date_source="deadline" if deadline else "",
        )

    @staticmethod
    def _event_url(value) -> str:
        if not isinstance(value, str):
            return ""
        url = urljoin("https://unstop.com/", value.strip())
        try:
            parsed = urlsplit(url)
        except ValueError:
            return ""
        parts = parsed.path.strip("/").split("/")
        if (parsed.scheme != "https" or parsed.hostname != "unstop.com"
                or len(parts) != 2 or parts[0] != "hackathons" or not parts[1]):
            return ""
        return url

    @staticmethod
    def _in_scope(item: dict) -> bool:
        """Ignore explicit remote/foreign venues, never the organiser's nationality."""
        if item.get("region") == "online":
            return False
        address = item.get("address_with_country_logo")
        country = address.get("country") if isinstance(address, dict) else None
        if isinstance(country, dict):
            code = country.get("alpha_2") or country.get("iso")
            if isinstance(code, str) and code.strip():
                return code.strip().lower() == "it"
            name = country.get("name")
            if isinstance(name, str) and name.strip():
                return name.strip().lower() in {"italy", "italia"}
        return True
