"""Eventbrite API for explicitly configured, authorized organizations.

Global event search was retired in 2019. A token alone cannot restore it;
public discovery is handled separately by the Eventbrite web collector.
"""

import logging
import re
from urllib.parse import urlsplit

import config
from models import BaseCollector, HackathonEvent
from utils.collector_health import record_issue
from utils.http import safe_get_json

logger = logging.getLogger(__name__)

API_BASE = "https://www.eventbriteapi.com/v3"
MAX_PAGES = 3


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _object(value: object) -> dict:
    return value if isinstance(value, dict) else {}


class EventbriteCollector(BaseCollector):

    @property
    def name(self) -> str:
        return "eventbrite"

    def collect(self) -> list[HackathonEvent]:
        organizations = getattr(config, "EVENTBRITE_ORGANIZATION_IDS", [])
        if not config.EVENTBRITE_API_KEY or not organizations:
            record_issue(
                "disabled",
                "Global event search retired; requires authorized organization IDs and API token",
            )
            logger.info("Eventbrite API: ricerca globale ritirata; organizzazioni autorizzate non configurate")
            return []

        if not isinstance(organizations, (list, tuple)) or any(
            not isinstance(value, str) or re.fullmatch(r"[0-9]+", value) is None
            for value in organizations
        ):
            record_issue("configuration_error", "EVENTBRITE_ORGANIZATION_IDS must contain numeric IDs")
            return []

        headers = {"Authorization": f"Bearer {config.EVENTBRITE_API_KEY}"}
        events: list[HackathonEvent] = []
        seen_ids: set[str] = set()
        for organization_id in dict.fromkeys(organizations):
            events.extend(self._collect_organization(organization_id, headers, seen_ids))

        logger.info("Eventbrite API: %d eventi pubblici dalle organizzazioni configurate", len(events))
        return events

    def _collect_organization(
        self, organization_id: str, headers: dict, seen_ids: set[str]
    ) -> list[HackathonEvent]:
        endpoint = f"{API_BASE}/organizations/{organization_id}/events/"
        events: list[HackathonEvent] = []
        continuation = ""
        seen_continuations: set[str] = set()

        for page in range(1, MAX_PAGES + 1):
            params = {
                "expand": "venue,organizer",
                "status": "live",
                "time_filter": "current_future",
                "page_size": 50,
            }
            if continuation:
                params["continuation"] = continuation
            else:
                params["page"] = page
            data = safe_get_json(endpoint, params=params, headers=headers)
            if data is None:
                break
            if not isinstance(data, dict) or not isinstance(data.get("events"), list):
                record_issue("parse_error", "Expected Eventbrite events list", endpoint)
                break

            for raw in data["events"]:
                event = self._parse_event(raw)
                if event is not None and event.id not in seen_ids:
                    seen_ids.add(event.id)
                    events.append(event)

            pagination = _object(data.get("pagination"))
            page_count = pagination.get("page_count")
            has_more = pagination.get("has_more_items")
            if not isinstance(has_more, bool):
                has_more = type(page_count) is int and page < page_count
            if not has_more:
                break
            if page == MAX_PAGES:
                record_issue("pagination_limit", "More organization events remain after page limit", endpoint)
                break
            continuation = _text(pagination.get("continuation"))
            if continuation:
                if continuation in seen_continuations:
                    record_issue("parse_error", "Repeated Eventbrite continuation token", endpoint)
                    break
                seen_continuations.add(continuation)

        return events

    def _parse_event(self, raw: object) -> HackathonEvent | None:
        if not isinstance(raw, dict):
            record_issue("parse_error", "Invalid Eventbrite event record")
            return None
        # Organization credentials can also read private drafts and invitations.
        if raw.get("listed") is not True or raw.get("status") != "live":
            return None
        if raw.get("invite_only") is True or raw.get("password") or raw.get("is_series_parent") is True:
            return None

        title = _text(_object(raw.get("name")).get("text"))
        url = _text(raw.get("url"))
        try:
            parts = urlsplit(url)
            valid_url = parts.scheme in {"http", "https"} and parts.hostname and not parts.username
        except ValueError:
            valid_url = False
        if not title or not valid_url:
            record_issue("parse_error", "Public Eventbrite event missing title or valid URL")
            return None

        description = _text(raw.get("summary")) or _text(_object(raw.get("description")).get("text"))
        start, end = _object(raw.get("start")), _object(raw.get("end"))
        date_str = ""
        if raw.get("hide_start_date") is not True:
            date_str = _text(start.get("local")) or _text(start.get("utc"))
        end_date = _text(end.get("local")) or _text(end.get("utc"))
        if date_str and end_date and raw.get("hide_end_date") is not True:
            date_str += f" — {end_date}"

        address = _object(_object(raw.get("venue")).get("address"))
        location = "Online" if raw.get("online_event") is True else _text(address.get("localized_address_display"))
        return HackathonEvent(
            title=title,
            url=url,
            source=self.name,
            description=description[:1000],
            date_str=date_str,
            date_source="event_api" if date_str else "unknown",
            published_at=_text(raw.get("published")),
            location=location,
            organizer=_text(_object(raw.get("organizer")).get("name")),
        )
