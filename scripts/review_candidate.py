#!/usr/bin/env python3
"""Admin workflow for published events and review candidates.

Usage:
    python scripts/review_candidate.py list
    python scripts/review_candidate.py list-events
    python scripts/review_candidate.py approve <candidate-id>
    python scripts/review_candidate.py reject <candidate-id>
    python scripts/review_candidate.py dismiss <candidate-id>
    python scripts/review_candidate.py remove <event-id-or-url-or-title-fragment> [--blacklist]
    python scripts/review_candidate.py move-to-review <event-id-or-url-or-title-fragment>
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

import config
from models import HackathonEvent
from storage.json_store import EventStore
from utils.html_export import generate_html
from utils.readme_export import generate_readme_table
from utils.review_queue import (
    load_review_decisions,
    load_review_queue,
    save_review_decisions,
    save_review_queue,
)

LOCAL_TZ = ZoneInfo("Europe/Rome")


def _now() -> datetime:
    return datetime.now(LOCAL_TZ)


def _append_blacklist_term(term: str) -> None:
    """Aggiunge un termine alla blacklist manuale se non presente."""
    path = getattr(config, "BLACKLIST_FILE", None)
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)

    existing: set[str] = set()
    if path.exists():
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip().lower()
            if not line or line.startswith("#"):
                continue
            existing.add(line)

    normalized = term.strip().lower()
    if not normalized or normalized in existing:
        return

    with open(path, "a", encoding="utf-8") as f:
        if path.stat().st_size > 0:
            f.write("\n")
        f.write(normalized)


def _find_event_to_remove(identifier: str, events: list[dict]) -> dict:
    key = identifier.strip().lower()
    if not key:
        raise SystemExit("Identifier cannot be empty")

    # 1) id prefix
    by_id = [e for e in events if str(e.get("id", "")).startswith(identifier)]
    if len(by_id) == 1:
        return by_id[0]
    if len(by_id) > 1:
        raise SystemExit(f"Ambiguous id prefix: {identifier}")

    # 2) exact/partial URL
    by_url = [e for e in events if key in str(e.get("url", "")).lower()]
    if len(by_url) == 1:
        return by_url[0]
    if len(by_url) > 1:
        raise SystemExit(f"Ambiguous URL fragment: {identifier}")

    # 3) title fragment
    by_title = [e for e in events if key in str(e.get("title", "")).lower()]
    if len(by_title) == 1:
        return by_title[0]
    if len(by_title) > 1:
        raise SystemExit(f"Ambiguous title fragment: {identifier}")

    raise SystemExit(f"No stored event matches: {identifier}")


def _resolve_candidate(candidate_id: str, queue: list[dict]) -> dict:
    matches = [item for item in queue if str(item.get("id", "")).startswith(candidate_id)]
    if not matches:
        raise SystemExit(f"No review candidate matches id prefix: {candidate_id}")
    if len(matches) > 1:
        raise SystemExit(f"Ambiguous id prefix: {candidate_id}")
    return matches[0]


def _event_from_candidate(candidate: dict) -> HackathonEvent:
    return HackathonEvent(
        title=candidate.get("title", ""),
        url=candidate.get("url", ""),
        source=candidate.get("source", ""),
        description=candidate.get("description", ""),
        date_str=candidate.get("date_str", ""),
        location=candidate.get("location", ""),
        organizer=candidate.get("organizer", ""),
        is_hackathon=True,
        confidence=float(candidate.get("confidence") or 0.0),
        review_status="manual_approved",
        review_reason=candidate.get("review_reason", "Manual review approved"),
        reviewed_at=_now().isoformat(),
        alternate_urls=candidate.get("alternate_urls", []),
        discovered_at=candidate.get("discovered_at") or _now().isoformat(),
    )


def _candidate_from_event(event: dict, note: str = "") -> dict:
    candidate = dict(event)
    candidate["review_status"] = "needs_review"
    candidate["queued_at"] = _now().isoformat()
    candidate["review_note"] = note or "Moved from published events by admin."
    candidate["review_reason"] = note or event.get("review_reason", "Admin requested re-review")
    return candidate


def _save_decision(candidate: dict, decision: str) -> None:
    decisions = load_review_decisions()
    decisions[candidate["id"]] = {
        "decision": decision,
        "title": candidate.get("title", ""),
        "url": candidate.get("url", ""),
        "reviewed_at": _now().isoformat(),
    }
    save_review_decisions(decisions)


def _clear_decision(candidate_id: str) -> None:
    decisions = load_review_decisions()
    if candidate_id in decisions:
        decisions.pop(candidate_id)
        save_review_decisions(decisions)


def _remove_from_queue(candidate: dict, queue: list[dict]) -> None:
    remaining = [item for item in queue if item.get("id") != candidate.get("id")]
    save_review_queue(remaining)


def _rebuild_site() -> None:
    generate_html()
    generate_readme_table()


def list_candidates() -> int:
    queue = load_review_queue()
    if not queue:
        print("No candidates waiting for manual review.")
        return 0

    for item in queue:
        candidate_id = item.get("id", "")[:12]
        confidence = float(item.get("confidence") or 0.0)
        title = item.get("title", "Untitled")
        source = item.get("source", "")
        reason = item.get("review_reason", "")
        print(f"{candidate_id}  {confidence:.2f}  {source}  {title}")
        if reason:
            print(f"  reason: {reason}")
    return 0


def list_events() -> int:
    store = EventStore()
    events = store.all_events()
    if not events:
        print("No published events.")
        return 0

    for item in events:
        event_id = str(item.get("id", ""))[:12]
        date = item.get("date_str") or "TBD"
        source = item.get("source", "")
        title = item.get("title", "Untitled")
        print(f"{event_id}  {date}  {source}  {title}")
    return 0


def approve_candidate(candidate_id: str) -> int:
    queue = load_review_queue()
    candidate = _resolve_candidate(candidate_id, queue)
    event = _event_from_candidate(candidate)

    store = EventStore()
    if not store.is_duplicate(event):
        store.add_event(event)
        store.save_with_timestamp(_now().isoformat())

    _save_decision(candidate, "approved")
    _remove_from_queue(candidate, queue)
    _rebuild_site()
    print(f"Approved: {event.title}")
    return 0


def reject_candidate(candidate_id: str) -> int:
    queue = load_review_queue()
    candidate = _resolve_candidate(candidate_id, queue)
    _save_decision(candidate, "rejected")
    _remove_from_queue(candidate, queue)
    _rebuild_site()
    print(f"Rejected: {candidate.get('title', 'Untitled')}")
    return 0


def dismiss_candidate(candidate_id: str) -> int:
    """Rimuove un candidato dalla coda senza decisione permanente."""
    queue = load_review_queue()
    candidate = _resolve_candidate(candidate_id, queue)
    _remove_from_queue(candidate, queue)
    _rebuild_site()
    print(f"Dismissed from review queue: {candidate.get('title', 'Untitled')}")
    return 0


def remove_event(identifier: str, add_blacklist: bool = False) -> int:
    """Rimuove un evento già pubblicato dallo storico e rigenera il sito."""
    store = EventStore()
    events = store.all_events()
    target = _find_event_to_remove(identifier, events)

    target_id = target.get("id")
    remaining = [e for e in events if e.get("id") != target_id]
    store.replace_events(remaining)
    store.save_with_timestamp(_now().isoformat())

    if add_blacklist:
        title = str(target.get("title", "")).strip()
        if title:
            _append_blacklist_term(title)

    _rebuild_site()
    print(f"Removed from published events: {target.get('title', 'Untitled')}")
    if add_blacklist:
        print("Added title to blacklist.")
    return 0


def move_event_to_review(identifier: str, note: str = "") -> int:
    """Sposta un evento pubblicato nella coda di revisione admin."""
    store = EventStore()
    events = store.all_events()
    target = _find_event_to_remove(identifier, events)
    target_id = target.get("id")

    queue = load_review_queue()
    if not any(item.get("id") == target_id for item in queue):
        queue.append(_candidate_from_event(target, note=note))
        save_review_queue(queue)

    remaining = [e for e in events if e.get("id") != target_id]
    store.replace_events(remaining)
    store.save_with_timestamp(_now().isoformat())
    _clear_decision(str(target_id))
    _rebuild_site()
    print(f"Moved to review: {target.get('title', 'Untitled')}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Admin workflow for hackathon events")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    sub.add_parser("list-events")

    approve = sub.add_parser("approve")
    approve.add_argument("candidate_id")

    reject = sub.add_parser("reject")
    reject.add_argument("candidate_id")

    dismiss = sub.add_parser("dismiss")
    dismiss.add_argument("candidate_id")

    remove = sub.add_parser("remove")
    remove.add_argument("identifier")
    remove.add_argument(
        "--blacklist",
        action="store_true",
        help="Add removed title to blacklist.txt to prevent re-ingestion",
    )

    move = sub.add_parser("move-to-review")
    move.add_argument("identifier")
    move.add_argument("--note", default="", help="Optional note shown in the review queue")

    args = parser.parse_args()
    if args.command == "list":
        return list_candidates()
    if args.command == "list-events":
        return list_events()
    if args.command == "approve":
        return approve_candidate(args.candidate_id)
    if args.command == "reject":
        return reject_candidate(args.candidate_id)
    if args.command == "dismiss":
        return dismiss_candidate(args.candidate_id)
    if args.command == "remove":
        return remove_event(args.identifier, add_blacklist=args.blacklist)
    if args.command == "move-to-review":
        return move_event_to_review(args.identifier, note=args.note)
    raise SystemExit(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
