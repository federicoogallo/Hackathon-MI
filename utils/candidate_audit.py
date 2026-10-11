"""Bounded local evidence for investigating discovery losses; never public event data."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from models import HackathonEvent
from utils.collector_health import public_endpoint


class CandidateAudit:
    def __init__(self):
        self.stages: list[dict] = []

    def stage(self, name: str, candidates: list[HackathonEvent], kept: list[HackathonEvent],
              reasons: dict[str, str] | None = None) -> None:
        accepted = {event.id for event in kept}
        records = []
        for event in candidates:
            records.append({
                "id": event.id, "source": event.source, "url": public_endpoint(event.url),
                "title": event.title[:400], "description": event.description[:2000],
                "date_str": event.date_str, "date_source": event.date_source,
                "published_at": event.published_at, "location": event.location,
                "outcome": "kept" if event.id in accepted else "excluded",
                "classification_status": event.classification_status,
                "reason": (reasons or {}).get(event.id, event.review_reason)[:500],
            })
        self.stages.append({"stage": name, "input": len(candidates), "output": len(kept), "records": records})

    def summary(self) -> list[dict]:
        return [{key: stage[key] for key in ("stage", "input", "output")} for stage in self.stages]

    def save(self, directory: str) -> None:
        if not directory:
            return
        folder = Path(directory)
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        stamp = datetime.now(timezone.utc)
        path = folder / f"candidates-{stamp.strftime('%Y%m%dT%H%M%S%fZ')}.json"
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump({"recorded_at": stamp.isoformat(), "stages": self.stages}, output,
                      ensure_ascii=False, indent=2)
        # Bound local retention without touching unrelated files.
        for old in sorted(folder.glob("candidates-*.json"), reverse=True)[30:]:
            old.unlink()
