#!/usr/bin/env python3
"""Cleanup deterministico dello store: quality gate + dedup fallback."""

from datetime import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import _deterministic_semantic_dedup_dicts, _passes_quality_gate
from models import HackathonEvent
from storage.json_store import EventStore
from utils.html_export import generate_html
from utils.readme_export import generate_readme_table


def run() -> None:
    store = EventStore()
    kept: list[dict] = []
    removed: list[tuple[str, str]] = []

    for item in store.all_events():
        ev = HackathonEvent(
            title=item.get("title", ""),
            url=item.get("url", ""),
            source=item.get("source", ""),
            description=item.get("description", ""),
            date_str=item.get("date_str", ""),
            location=item.get("location", ""),
            organizer=item.get("organizer", ""),
        )
        ok, reason = _passes_quality_gate(ev)
        if ok:
            kept.append(item)
        else:
            removed.append((ev.title, reason))

    before = len(kept)
    kept = _deterministic_semantic_dedup_dicts(kept)
    dedup_removed = before - len(kept)

    store.replace_events(kept)
    store.save_with_timestamp(datetime.now().isoformat())

    generate_html()
    generate_readme_table()

    print(f"removed_by_quality={len(removed)}")
    for title, reason in removed:
        print(f"- {title[:90]} | {reason}")
    print(f"dedup_removed={dedup_removed}")
    print(f"final_store_count={store.count}")


if __name__ == "__main__":
    run()
