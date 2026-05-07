#!/usr/bin/env python3
"""Local maintainer entrypoint for event/review administration."""

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from scripts.review_candidate import main


if __name__ == "__main__":
    raise SystemExit(main())
