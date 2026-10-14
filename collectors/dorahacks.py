"""DoraHacks public listing; access challenges remain visible in source health."""

import json
import logging
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from models import BaseCollector, HackathonEvent
from utils.collector_health import record_issue
from utils.http import safe_get

logger = logging.getLogger(__name__)
DORAHACKS_URL = "https://dorahacks.io/hackathon"


class DoraHacksCollector(BaseCollector):
    @property
    def name(self) -> str:
        return "dorahacks"

    def collect(self) -> list[HackathonEvent]:
        # The former /api/hackathon/list endpoint no longer exists. Do not retry
        # alternate hosts or imitate a browser when the public site denies access.
        response = safe_get(DORAHACKS_URL)
        if response is None:
            return []
        soup = BeautifulSoup(response.text, "lxml")
        if soup.title and "human verification" in soup.title.get_text().lower():
            record_issue("blocked", "public listing requires human verification", DORAHACKS_URL)
            return []
        events = []
        seen = set()
        recognised = False
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.get_text())
            except (ValueError, TypeError):
                continue
            nodes = data if isinstance(data, list) else [data]
            while nodes:
                node = nodes.pop(0)
                if not isinstance(node, dict):
                    continue
                if isinstance(node.get("@graph"), list):
                    nodes.extend(node["@graph"])
                if node.get("@type") == "ItemList" and isinstance(node.get("itemListElement"), list):
                    items = node["itemListElement"]
                    readable = []
                    for item in items:
                        candidate = item.get("item", item) if isinstance(item, dict) else None
                        if (isinstance(candidate, dict) and candidate.get("@type") == "Event"
                                and self._parse_item(candidate, set())):
                            readable.append(candidate)
                    if items and not readable:
                        record_issue("parse_error", "nonempty ItemList has no readable events", DORAHACKS_URL)
                    else:
                        recognised = True
                    nodes.extend(readable)
                if node.get("@type") == "ListItem" and isinstance(node.get("item"), dict):
                    nodes.append(node["item"])
                if node.get("@type") == "Event":
                    event = self._parse_item(node, set())
                    if event:
                        recognised = True
                        if event.url not in seen:
                            seen.add(event.url)
                            events.append(event)
        if not recognised:
            record_issue("parse_error", "public listing has no supported event data", DORAHACKS_URL)
        logger.info("DoraHacks: trovati %d candidati", len(events))
        return events

    def _parse_item(self, item: dict, seen_urls: set[str]) -> HackathonEvent | None:
        title, url = item.get("name"), item.get("url")
        if not isinstance(title, str) or not title.strip() or not isinstance(url, str):
            return None
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname != "dorahacks.io" or not parsed.path.startswith("/hackathon/") or url in seen_urls:
            return None
        loc = item.get("location")
        location = ""
        if isinstance(loc, str):
            location = loc
        elif isinstance(loc, dict):
            address = loc.get("address")
            if isinstance(address, dict):
                location = ", ".join(str(address[k]) for k in ("addressLocality", "addressCountry") if address.get(k))
            if not location and isinstance(loc.get("name"), str):
                location = loc["name"]
        date = item.get("startDate") if isinstance(item.get("startDate"), str) else ""
        description = item.get("description") if isinstance(item.get("description"), str) else ""
        seen_urls.add(url)
        return HackathonEvent(title=title.strip(), url=url, source=self.name, description=description[:500],
                              date_str=date, date_source="event_jsonld" if date else "", location=location)
