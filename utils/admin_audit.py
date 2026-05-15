"""Structured audit log for admin decisions."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import config
from models import HackathonEvent

LOCAL_TZ = ZoneInfo("Europe/Rome")

REJECT_ACTIONS = {"rejected", "removed"}
PUBLISH_ACTIONS = {"approved"}

REASON_CODES = (
    "valid_milan_event",
    "online_only",
    "not_milan",
    "past_or_finished",
    "missing_date_or_venue",
    "duplicate",
    "not_hackathon",
    "source_noise",
    "known_false_positive",
    "other",
)


def _now_iso() -> str:
    return datetime.now(LOCAL_TZ).isoformat()


def _path(path: Path | None = None) -> Path:
    return path or config.ADMIN_ACTIONS_FILE


def _normalize_reason_code(reason_code: str) -> str:
    normalized = (reason_code or "").strip().lower().replace("-", "_")
    if not normalized:
        return "other"
    if normalized not in REASON_CODES:
        return "other"
    return normalized


def load_admin_actions(path: Path | None = None) -> list[dict[str, Any]]:
    """Load admin actions. Missing or malformed files are treated as empty."""
    action_path = _path(path)
    if not action_path.exists():
        return []

    try:
        payload = json.loads(action_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    actions = payload.get("actions", [])
    if not isinstance(actions, list):
        return []
    return [item for item in actions if isinstance(item, dict)]


def save_admin_actions(actions: list[dict[str, Any]], path: Path | None = None) -> Path:
    action_path = _path(path)
    action_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": _now_iso(),
        "count": len(actions),
        "actions": actions,
    }
    action_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return action_path


def _snapshot(event: HackathonEvent | dict[str, Any]) -> dict[str, Any]:
    if isinstance(event, HackathonEvent):
        data = event.to_dict()
    else:
        data = dict(event)

    return {
        "id": data.get("id", ""),
        "title": data.get("title", ""),
        "url": data.get("url", ""),
        "source": data.get("source", ""),
        "description": data.get("description", ""),
        "date_str": data.get("date_str", ""),
        "location": data.get("location", ""),
        "organizer": data.get("organizer", ""),
        "confidence": data.get("confidence", 0.0),
    }


def _expected_for_action(action: str) -> str:
    if action in REJECT_ACTIONS:
        return "reject"
    if action in PUBLISH_ACTIONS:
        return "publish"
    return "review"


def record_admin_action(
    action: str,
    event: HackathonEvent | dict[str, Any],
    *,
    reason: str = "",
    reason_code: str = "",
    regression: bool = False,
    path: Path | None = None,
) -> dict[str, Any]:
    """Append a structured admin decision and return the recorded item."""
    normalized_action = action.strip().lower().replace("-", "_")
    item = {
        **_snapshot(event),
        "action": normalized_action,
        "expected": _expected_for_action(normalized_action),
        "reason": reason.strip(),
        "reason_code": _normalize_reason_code(reason_code),
        "regression": bool(regression),
        "created_at": _now_iso(),
    }

    actions = load_admin_actions(path)
    actions.append(item)
    save_admin_actions(actions, path)
    return item


def admin_regression_cases(path: Path | None = None) -> list[dict[str, Any]]:
    """Return admin decisions explicitly marked as regression cases."""
    return [item for item in load_admin_actions(path) if item.get("regression") is True]


def event_from_admin_action(action: dict[str, Any]) -> HackathonEvent:
    """Build a HackathonEvent from an admin action snapshot."""
    return HackathonEvent(
        title=action.get("title", ""),
        url=action.get("url", ""),
        source=action.get("source", "admin_action"),
        description=action.get("description", ""),
        date_str=action.get("date_str", ""),
        location=action.get("location", ""),
        organizer=action.get("organizer", ""),
        is_hackathon=True,
        confidence=float(action.get("confidence") or 0.0),
    )
