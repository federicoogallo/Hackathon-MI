"""
Collector Devpost — API pubblica richiamata dalla pagina hackathon.

Endpoint: https://devpost.com/api/hackathons
Le risposte fuzzy senza riferimenti geografici vengono escluse.
"""

import json
import logging
import re
from urllib.parse import urlsplit

from models import BaseCollector, HackathonEvent
from utils.http import safe_get
from utils.collector_health import record_issue

logger = logging.getLogger(__name__)

DEVPOST_API_URL = "https://devpost.com/api/hackathons"
DEVPOST_QUERIES = ("milan", "milano", "italy")


class DevpostCollector(BaseCollector):

    @property
    def name(self) -> str:
        return "devpost"

    def collect(self) -> list[HackathonEvent]:
        events: list[HackathonEvent] = []
        seen: set[str] = set()
        for query in DEVPOST_QUERIES:
            for page in range(1, 4):
                response = safe_get(DEVPOST_API_URL, params={
                    "search": query, "status[]": ["open", "upcoming"], "page": page,
                })
                if response is None:
                    break
                try:
                    payload = json.loads(response.text)
                except (ValueError, TypeError):
                    record_issue("parse_error", "invalid hackathon API JSON", DEVPOST_API_URL)
                    break
                if not isinstance(payload, dict) or not isinstance(payload.get("hackathons"), list):
                    record_issue("parse_error", "unexpected hackathon API schema", DEVPOST_API_URL)
                    break
                items = payload["hackathons"]
                meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
                for item in items:
                    event = self._parse_api_item(item, seen, fuzzy=meta.get("fuzzy") is True)
                    if event:
                        events.append(event)
                total, per_page = meta.get("total_count"), meta.get("per_page")
                if not items or (isinstance(total, int) and isinstance(per_page, int)
                                 and per_page > 0 and page * per_page >= total):
                    break
        logger.info("Devpost: trovati %d candidati", len(events))
        return events

    def _parse_api_item(self, item, seen_urls: set[str], *, fuzzy=False) -> HackathonEvent | None:
        if not isinstance(item, dict):
            return None
        title, url = item.get("title"), item.get("url")
        if not isinstance(title, str) or not title.strip() or not isinstance(url, str):
            return None
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not (parsed.hostname or "").endswith(".devpost.com") or url in seen_urls:
            return None
        loc = item.get("displayed_location")
        location = loc.get("location", "") if isinstance(loc, dict) else ""
        organizer = item.get("organization_name", "")
        # Devpost returns unrelated suggestions when no exact search matches exist.
        if fuzzy and not re.search(r"\b(?:milan|milano|italy|italia)\b", f"{title} {location} {organizer}", re.I):
            return None
        themes = item.get("themes") if isinstance(item.get("themes"), list) else []
        topics = ", ".join(t["name"] for t in themes if isinstance(t, dict) and isinstance(t.get("name"), str))
        submission = item.get("submission_period_dates", "")
        seen_urls.add(url)
        return HackathonEvent(
            title=title.strip(), url=url, source=self.name, location=location, organizer=organizer,
            description=f"Hackathon. {topics}. Periodo di invio progetti: {submission}".strip(),
            # Submission deadlines are not reliable physical event dates.
            date_str=submission if isinstance(submission, str) else "", date_source="deadline",
        )
