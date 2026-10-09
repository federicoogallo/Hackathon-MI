#!/usr/bin/env python3
"""Build GitHub Pages redirects and refresh the README event table.

Writes `docs/index.html` and `docs/review.html` as redirects to the canonical
Next.js site. The README table is refreshed from `data/events.json` without
running collection, classification or notifications.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from utils.html_export import generate_html
from utils.readme_export import generate_readme_table


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("build-static-site")


def main() -> int:
    logger.info("Building GitHub Pages redirects to the canonical site")
    html_path = generate_html()
    logger.info("Generated: %s", html_path)

    logger.info("Refreshing README table")
    readme_path = generate_readme_table()
    logger.info("Generated: %s", readme_path)

    logger.info("Redirect pages and README table updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
