#!/usr/bin/env python3
"""One-off repair of archive aliases attached by the pre-2026-10-11 matcher.

Until commit d926560 the store treated shared fragments such as "11 00 am" or
"in to your" as the same event, and saved the matching page as an alias: login
pages, foreign Meetup events and unrelated news. Aliases are identity keys, so
they kept discarding new candidates as "already known".

    python scripts/repair_alternate_urls.py           # show what would change
    python scripts/repair_alternate_urls.py --apply   # rewrite data/events.json

See utils.event_identity.prune_unrelated_alternate_urls for the rule.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from utils.event_identity import prune_unrelated_alternate_urls  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="write the repaired archive")
    args = parser.parse_args()

    path = config.EVENTS_FILE
    data = json.loads(path.read_text(encoding="utf-8"))
    repaired_events, total_dropped = [], 0
    for event in data.get("events", []):
        repaired, dropped = prune_unrelated_alternate_urls(event)
        repaired_events.append(repaired)
        total_dropped += len(dropped)
        if dropped:
            print(f"{event.get('title', '')[:70]}: {len(dropped)} removed, {len(repaired['alternate_urls'])} kept")
            for url in dropped[:5]:
                print(f"    - {url[:110]}")
            if len(dropped) > 5:
                print(f"    … {len(dropped) - 5} more")

    print(f"{total_dropped} aliases removed from {len(repaired_events)} events")
    if args.apply and total_dropped:
        data["events"] = repaired_events
        # Same layout as storage.json_store, so the diff shows only the aliases.
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"-> {path}")


if __name__ == "__main__":
    main()
