from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

import pytest

from utils.html_export import _sort_key, generate_html


class _PageElements(HTMLParser):
    def __init__(self, text: str):
        super().__init__()
        self.elements: list[tuple[str, dict]] = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


@pytest.mark.parametrize("origin", [
    "https://hackathon-milano.vercel.app",
    "https://hackathon.example.org",
])
def test_pages_redirect_to_the_corresponding_canonical_route(tmp_path: Path, origin: str):
    index = tmp_path / "public" / "index.html"
    review = tmp_path / "public" / "review.html"
    archive = tmp_path / "events.json"
    # Invalid archive contents must not prevent visitors reaching the main site.
    archive.write_text("invalid archive", encoding="utf-8")
    with patch("utils.html_export.SITE_URL", origin):
        result = generate_html(archive, index, review)

    assert result == index
    for page, route in [(index, "/"), (review, "/review")]:
        elements = _PageElements(page.read_text(encoding="utf-8")).elements
        destination = f"{origin}{route}"
        assert any(tag == "meta" and attrs.get("http-equiv") == "refresh"
                   and attrs.get("content") == f"0; url={destination}"
                   for tag, attrs in elements)
        assert any(tag == "link" and attrs.get("rel") == "canonical"
                   and attrs.get("href") == destination for tag, attrs in elements)
        assert any(tag == "a" and attrs.get("href") == destination
                   for tag, attrs in elements)
        assert not any(tag in {"script", "iframe"} for tag, _ in elements)


def test_redirects_work_without_an_event_archive(tmp_path: Path):
    index = tmp_path / "index.html"
    review = tmp_path / "review.html"
    generate_html(tmp_path / "missing.json", str(index), str(review))
    assert index.is_file()
    assert review.is_file()


def test_admin_server_date_sorting_remains_available():
    assert _sort_key({"date_str": "2099-06-15"}) == date(2099, 6, 15)
    assert _sort_key({"date_str": "TBD"}) == date.max
