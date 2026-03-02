#!/usr/bin/env python3
"""Rimuove falsi positivi (non-Milano) dall'events.json e rigenera HTML."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.html_export import generate_html

p = Path(__file__).parent.parent / "data" / "events.json"
d = json.loads(p.read_text())
before = len(d["events"])

# Substring URL da rimuovere (falsi positivi del modello 8B — non-Milano)
remove_substrings = [
    "karar.com",
    "tailormadehackathon.com",
    "agacgfm.org",
    "makeuoft.ca",
    "stonehill.in",
    "datathon.ai",
    "lstat.kuleuven.be",
    "genchackathon.gsb.gov.tr",
    "yumpu.com",
    "thetopvoices.com",
    "ctftime.org",
    "taikai.network/en/cassinihackathons",
    "dfglake.gr",
]

remove_ids = set()
for e in d["events"]:
    url = e.get("url", "")
    for sub in remove_substrings:
        if sub in url:
            remove_ids.add(e["id"])
            print(f"  RIMOSSO: {e['title'][:60]} ({sub})")
            break

d["events"] = [e for e in d["events"] if e["id"] not in remove_ids]
after = len(d["events"])

p.write_text(json.dumps(d, indent=2, ensure_ascii=False))
print(f"\nRimossi {before - after} falsi positivi: {before} -> {after}")

# Rigenera HTML
generate_html()
print("HTML rigenerata")

# Mostra eventi rimasti
print(f"\n=== {after} EVENTI CONFERMATI ===")
for i, e in enumerate(d["events"]):
    loc = e.get("location", "") or "(vuota)"
    print(f"{i+1:2d}. {e['title'][:60]}")
    print(f"    loc={loc[:55]}")
    print(f"    {e['url'][:80]}")
    print()
