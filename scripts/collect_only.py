#!/usr/bin/env python3
"""Step 1: Solo raccolta + keyword filter, salva candidati."""
import sys, json, logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("collect-only")

from scripts.slow_classify import collect_all
from filters.keyword_filter import keyword_filter_batch

logger.info("=== RACCOLTA EVENTI ===")
all_events = collect_all()
logger.info("Totale raw: %d", len(all_events))

seen = set()
unique = []
for e in all_events:
    if e.id not in seen:
        seen.add(e.id)
        unique.append(e)
logger.info("Post dedup: %d", len(unique))

kw_passed, kw_disc = keyword_filter_batch(unique)
logger.info("Post keyword: %d passati, %d scartati", len(kw_passed), kw_disc)

pre = len(kw_passed)
kw_passed = [e for e in kw_passed if e.is_upcoming()]
logger.info("Post date: %d -> %d", pre, len(kw_passed))

data = [
    {"title": e.title, "url": e.url, "source": e.source,
     "description": e.description, "date_str": e.date_str, "location": e.location}
    for e in kw_passed
]
Path("/tmp/hackathon_candidates.json").write_text(json.dumps(data, indent=2, ensure_ascii=False))
logger.info("Salvati %d candidati in /tmp/hackathon_candidates.json", len(kw_passed))

print("\n=== CANDIDATI ===")
for i, e in enumerate(kw_passed):
    print(f"{i+1:3d}. [{e.source}] {e.title[:70]}")
    print(f"     {e.url[:90]}")
    print(f"     loc={e.location or '(vuota)'}, date={e.date_str or '(vuota)'}")
    print()
