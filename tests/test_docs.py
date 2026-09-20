"""Regression checks for generated README content and maintainer documentation."""

import json
import re
from pathlib import Path

from utils.readme_export import TABLE_END, TABLE_START, generate_readme_table


ROOT = Path(__file__).parents[1]


def test_readme_has_single_generated_region():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert text.count(TABLE_START) == 1
    assert text.count(TABLE_END) == 1
    assert text.index(TABLE_START) < text.index(TABLE_END)


def test_documentation_relative_links_exist():
    for document in ("README.md", "docs/setup.md", "docs/admin.md", "docs/newsletter.md"):
        path = ROOT / document
        text = path.read_text(encoding="utf-8")
        for target in re.findall(r"\[[^\]]+\]\(([^\s)]+)\)", text):
            if "://" in target or target.startswith("#"):
                continue
            target = target.split("#", 1)[0]
            assert (path.parent / target).exists(), f"Broken link in {document}: {target}"


def test_readme_regeneration_preserves_prose_and_literal_event_text(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(f"# Project\n\nBefore\n{TABLE_START}\nold table\n{TABLE_END}\nAfter\n")
    events = tmp_path / "events.json"
    events.write_text(json.dumps({"events": [{
        "title": r"Build \Unity | Milan",
        "url": "https://example.org/hackathon",
        "source": "web_search",
        "location": "Milano",
        "date_str": "2099-10-12",
        "is_hackathon": True,
    }]}))

    generate_readme_table(events, readme)
    result = readme.read_text()

    assert result.startswith("# Project\n\nBefore\n")
    assert result.endswith("\nAfter\n")
    assert r"Build \Unity \| Milan" in result
    assert "| Web search |" in result
    assert "old table" not in result
