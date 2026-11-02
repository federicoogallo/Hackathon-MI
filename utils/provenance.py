"""Identify the code and the scan behind each recorded decision."""

import os
import subprocess
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def pipeline_commit() -> str:
    """Commit the pipeline runs from: GitHub's SHA in Actions, else the local checkout."""
    sha = os.environ.get("GITHUB_SHA", "").strip()
    if sha:
        return sha
    try:
        return subprocess.check_output(
            ["git", "-C", str(_ROOT), "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL, text=True, timeout=5,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def scan_id(started_at: datetime | None = None) -> str:
    """GitHub run (and attempt) in Actions; a local timestamp otherwise."""
    run = os.environ.get("GITHUB_RUN_ID", "").strip()
    if run:
        attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1").strip() or "1"
        return f"gh-{run}" if attempt == "1" else f"gh-{run}-{attempt}"
    stamp = (started_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return f"local-{stamp.strftime('%Y%m%dT%H%M%SZ')}"
