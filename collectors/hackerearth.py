"""Public Compete API used by HackerEarth's current challenges page."""

import logging
import re
from urllib.parse import urljoin, urlsplit

from models import BaseCollector, HackathonEvent
from utils.collector_health import record_issue
from utils.http import safe_get_json

logger = logging.getLogger(__name__)
HACKEREARTH_API_URL = "https://www.hackerearth.com/api/community/challenges/compete/"


class HackerEarthCollector(BaseCollector):
    @property
    def name(self) -> str:
        return "hackerearth"

    def collect(self) -> list[HackathonEvent]:
        payload = safe_get_json(HACKEREARTH_API_URL)
        if payload is None:
            return []
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            record_issue("parse_error", "unexpected Compete API schema", HACKEREARTH_API_URL)
            return []
        seen: set[str] = set()
        events = [event for item in payload["data"] if (event := self._parse_item(item, seen))]
        logger.info("HackerEarth: trovati %d candidati", len(events))
        return events

    def _parse_item(self, item, seen_urls: set[str]) -> HackathonEvent | None:
        if not isinstance(item, dict):
            return None
        title = item.get("title")
        href = item.get("url")
        kind = item.get("type", "")
        if not isinstance(title, str) or not isinstance(href, str) or not title.strip():
            return None
        if kind != "Hackathon" and not re.search(r"\b(?:hackathon|datathon|makeathon)\b", title, re.I):
            return None
        url = urljoin(HACKEREARTH_API_URL, href)
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname != "www.hackerearth.com" or not parsed.path.startswith("/challenges/") or url in seen_urls:
            return None
        start = item.get("start") if isinstance(item.get("start"), str) else ""
        end = item.get("end") if isinstance(item.get("end"), str) else ""
        date_str = f"{start} — {end}" if start and end and start != end else start
        seen_urls.add(url)
        return HackathonEvent(
            title=title.strip(), url=url, source=self.name, date_str=date_str,
            date_source="event_api" if start else "", organizer=item.get("company_name", ""),
            description=f"{kind}. Organizzato da {item.get('company_name', '')}".strip(),
            # The global listing does not provide a physical venue.
            location="",
        )
