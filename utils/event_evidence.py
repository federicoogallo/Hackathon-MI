"""Bounded, read-only evidence retrieval for promising search results.

Dates are accepted only from Event JSON-LD. Publication dates stay separate;
page prose is evidence for review, never a source of inferred event facts.
"""

import ipaddress
import json
import logging
import re
import socket
import time
from datetime import datetime
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from models import HackathonEvent, _normalize_title
from utils.event_identity import _identity_url, editions_compatible, same_event

logger = logging.getLogger(__name__)
MAX_PAGE_BYTES = 768_000
MAX_FETCH_SECONDS = 12
MAX_REDIRECTS = 2
_EVENT_TERMS = re.compile(r"hackathon|datathon|buildathon|makeathon|ideathon|coding challenge|game jam", re.I)
_CONTEXT_TERMS = re.compile(r"hackathon|datathon|buildathon|challenge|bocconi|bainsa|milano?\b|talent garden|\b20\d{2}\b", re.I)
_SOCIAL_HOSTS = {"facebook.com", "instagram.com", "linkedin.com", "tiktok.com", "youtube.com", "x.com", "twitter.com"}
_EVIDENCE_DOMAINS = frozenset({
    "unibocconi.it", "polimi.it", "unimib.it", "unicatt.it", "iulm.it", "unisr.it",
    "luma.com", "lu.ma", "eventbrite.it", "eventbrite.com", "devpost.com", "meetup.com",
    "bo-om.it", "polihub.it", "cariplofactory.it", "fondazionetriulza.org", "telespazio.com",
    "anthropic.com", "claude.com", "openapi.com", "talentgarden.com",
})


def _known_host(host: str) -> bool:
    return any(host == domain or host.endswith("." + domain) for domain in _EVIDENCE_DOMAINS)


def is_promising_result(event: HackathonEvent) -> bool:
    """Do not spend the fetch budget on generic listings or social login walls."""
    parsed = urlparse(event.url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not host:
        return False
    if any(host == domain or host.endswith("." + domain) for domain in _SOCIAL_HOSTS):
        return False
    if not _known_host(host):
        return False
    return bool(_EVENT_TERMS.search(f"{event.title} {event.description} {parsed.path}"))


def _public_url(url: str) -> bool:
    """Reject local destinations and credentials, including on redirects."""
    try:
        parsed = urlparse(url)
        host = parsed.hostname
        if parsed.scheme not in {"http", "https"} or not host or not _known_host(host.lower()) or parsed.username or parsed.password:
            return False
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if port not in {80, 443} or host.lower() == "localhost" or host.lower().endswith((".localhost", ".local", ".internal")):
            return False
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        return bool(addresses) and all(ipaddress.ip_address(item[4][0]).is_global for item in addresses)
    except (ValueError, OSError):
        return False


def fetch_public_html(url: str) -> str | None:
    """One bounded attempt: no retries, cookies, JS, authentication or bot bypass."""
    started = time.monotonic()
    # The general collector client follows redirects and retries. Evidence fetches
    # need explicit destination validation and a much smaller independent budget.
    with requests.Session() as session:
        session.trust_env = False
        for _ in range(MAX_REDIRECTS + 1):
            if not _public_url(url) or time.monotonic() - started >= MAX_FETCH_SECONDS:
                return None
            try:
                session.cookies.clear()
                with session.get(
                    url, timeout=(3, 5), allow_redirects=False, stream=True,
                    headers={
                        "User-Agent": "HackathonMilanoMonitor/1.0 (+https://hackathon-milano.vercel.app)",
                        "Accept": "text/html,application/xhtml+xml",
                    },
                ) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        target = response.headers.get("Location")
                        if not target:
                            return None
                        url = urljoin(url, target)
                        continue
                    if response.status_code != 200:
                        return None
                    if not any(kind in response.headers.get("Content-Type", "").lower() for kind in ("text/html", "application/xhtml+xml")):
                        return None
                    body = bytearray()
                    size = 0
                    # Check the budget as bytes arrive. Large blocking reads can
                    # wait indefinitely on a server that slowly trickles data.
                    # One final socket read can exceed the budget by its 5s timeout.
                    for chunk in response.iter_content(chunk_size=1):
                        size += len(chunk)
                        if size > MAX_PAGE_BYTES or time.monotonic() - started >= MAX_FETCH_SECONDS:
                            return None
                        body.extend(chunk)
                    return body.decode(response.encoding or "utf-8", errors="replace")
            except requests.RequestException:
                logger.debug("Evidence page unavailable for host %s", urlparse(url).hostname)
                return None
    return None


def _event_nodes(value, depth: int = 0) -> list[dict]:
    if depth > 12:
        return []
    if isinstance(value, list):
        return [node for item in value for node in _event_nodes(item, depth + 1)]
    if not isinstance(value, dict):
        return []
    types = value.get("@type", [])
    if isinstance(types, str):
        types = [types]
    if not isinstance(types, list):
        types = []
    if any(isinstance(kind, str) and kind.rsplit("/", 1)[-1] == "Event" for kind in types):
        return [value]
    return [node for child in value.values() for node in _event_nodes(child, depth + 1)]


def _iso_date(value) -> str:
    if not isinstance(value, str) or not re.match(r"^\d{4}-\d{2}-\d{2}(?:T.*)?$", value):
        return ""
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value
    except ValueError:
        return ""


def _plain(value, limit: int = 1000) -> str:
    return BeautifulSoup(value, "lxml").get_text(" ", strip=True)[:limit] if isinstance(value, str) else ""


def _location(value) -> str:
    if isinstance(value, str):
        return _plain(value, 300)
    if not isinstance(value, dict):
        return ""
    parts = [_plain(value.get("name"), 150)]
    address = value.get("address", {})
    if isinstance(address, str):
        parts.append(address)
    elif isinstance(address, dict):
        parts.extend(_plain(address.get(key), 150) for key in ("streetAddress", "addressLocality", "addressRegion", "addressCountry"))
    return ", ".join(dict.fromkeys(part for part in parts if part))[:400]


def _matches_event(node: dict, event: HackathonEvent) -> bool:
    """A single embedded Event is not automatically the search result's event."""
    node_title = _plain(node.get("name"), 300)
    node_url = node.get("url")
    candidate = {
        "title": node_title,
        "url": urljoin(event.url, node_url) if isinstance(node_url, str) else "",
        "date_str": _iso_date(node.get("startDate")),
        "date_source": "event_jsonld",
    }
    if not editions_compatible(event, candidate):
        return False
    if candidate["url"] and _identity_url(candidate["url"]) in {
        _identity_url(url) for url in [event.url, *event.alternate_urls]
    }:
        return True
    # Exact, nontrivial names also work when JSON-LD omits url (common on Luma).
    normalized = _normalize_title(node_title)
    if len(normalized) >= 12 and len(normalized.split()) >= 2 and normalized == _normalize_title(event.title):
        return True
    return bool(node_title) and same_event(event, candidate)


def enrich_from_html(event: HackathonEvent, html: str) -> bool:
    """Add explicitly sourced facts; leave absent/ambiguous facts untouched."""
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(" ", strip=True).lower() if soup.title else ""
    if any(marker in title for marker in ("just a moment", "access denied", "verify you are human", "attention required")):
        return False
    nodes = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            nodes.extend(_event_nodes(json.loads(tag.string or tag.get_text())))
        except (ValueError, RecursionError):
            continue
    matches = [node for node in nodes if _matches_event(node, event)]
    selected = matches[0] if len(matches) == 1 else None

    changed = False
    evidence = []
    if selected:
        start = _iso_date(selected.get("startDate"))
        end = _iso_date(selected.get("endDate"))
        if start:
            event.date_str = f"{start} — {end}" if end and end >= start else start
            event.date_source = "event_jsonld"
            changed = True
        location = _location(selected.get("location"))
        if location:
            event.location = location
            changed = True
        description = _plain(selected.get("description"))
        if description:
            evidence.append(description)
        attendance = selected.get("eventAttendanceMode", "")
        if isinstance(attendance, str) and attendance.endswith("OnlineEventAttendanceMode"):
            evidence.append("Online-only event (Event JSON-LD).")

    publication = soup.find("meta", property="article:published_time")
    if publication:
        published_at = _iso_date(publication.get("content"))
        if published_at:
            event.published_at = published_at
            changed = True

    for removable in soup.select("script, style, nav, footer, header, aside, form"):
        removable.decompose()
    content = soup.find("main") or soup.find("article") or soup.body
    if content:
        for block in content.find_all(["h1", "h2", "h3", "p", "li"]):
            text = block.get_text(" ", strip=True)
            if 15 <= len(text) <= 1500 and _CONTEXT_TERMS.search(text):
                evidence.append(text)
            if sum(len(part) for part in evidence) >= 1400:
                break
    if evidence:
        event.description = "\n".join(dict.fromkeys(evidence + [event.description]))[:1800]
        changed = True
    return changed


def enrich_event_evidence(event: HackathonEvent) -> bool:
    html = fetch_public_html(event.url)
    return enrich_from_html(event, html) if html else False
