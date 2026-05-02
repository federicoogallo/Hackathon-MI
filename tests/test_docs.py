"""
Test di coerenza per documentazione generata/manuale.
"""

import re
from pathlib import Path

from main import get_collectors


def test_readme_source_count_matches_registered_collectors():
    """Il README deve restare allineato al registry dei collector."""
    readme = Path(__file__).parents[1] / "README.md"
    text = readme.read_text(encoding="utf-8")
    expected = len(get_collectors())

    assert f"from {expected} heterogeneous sources" in text
    assert f"Collectors ({expected} sources in parallel)" in text
    assert f"sources-{expected}-green" in text

    listed_numbers = [
        int(match.group(1))
        for match in re.finditer(r"^\| (\d+) \| \*\*", text, re.MULTILINE)
    ]
    assert max(listed_numbers) == expected
