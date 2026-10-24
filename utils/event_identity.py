"""Conservative, deterministic event identity shared by collection and storage.

A common topic is not an identity. Dates and explicit editions must agree
before titles can identify the same event. Raw records sharing a URL are
consolidated before filtering so collector completion order cannot lose facts.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import fields
from difflib import SequenceMatcher
import logging
import json
import re
from typing import Any, Mapping
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

import config
from models import HackathonEvent, _normalize_title, _normalize_url

logger = logging.getLogger(__name__)
EventLike = HackathonEvent | Mapping[str, Any]

# Topics, event formats, editorial wording and venue words are not a brand.
_GENERIC = frozenset("""
    a an the for and with from that this will have has are was were been being
    about into your our their which what when where how of in on at to by as
    il lo la le gli i un una uno del dei delle degli per con alla alle allo
    agli che nel nella sono come dal dalla anche tra più suo suoi loro questo
    questa essere fare dire non tutto tutti sul si di ed al arriva arriva
    hackathon hack challenge competition contest event events evento eventi
    league weekend day days jam sprint marathon maratona giornata giorni sfida
    coding code programming programmazione software technology technologies
    tecnologia tecnologie tech innovation innovazione innovative innovativo
    innovativi digital digitale data dati ai ia artificial intelligence
    intelligenza artificiale future futuro building build product sviluppo
    developer developers team teams community online physical virtual local
    milano milan italy italia lombardia university università politecnico
    student students studenti progetto progetti iniziative open edition edizione
    registration register reminder announcement announced news tickets biglietti
    ospita presenta presents present participate partecipare new nuovo nuova
    it en org com www http https italia italiano internazionale international
    sostenibilità sustainability sustainable sostenibile social sociale good
    machine learning deep accessibility accessibilità
    club society societa società universitario universitaria universitari universitarie
""".split())
# These terms cannot establish identity, but a change of topic must still count
# against a fuzzy match between two events by the same organizer.
_TOPICS = frozenset("""
    software technology technologies tecnologia tecnologie tech innovation
    innovazione innovative innovativo innovativi digital digitale data dati ai ia
    artificial intelligence intelligenza artificiale future futuro building
    build product sviluppo developer developers community open sustainability
    sostenibilità sustainable sostenibile social sociale good machine learning
    deep accessibility accessibilità
""".split())
_YEAR = re.compile(r"\b20\d{2}\b")
_EDITION = re.compile(
    r"\b(?:edizione|edition)\s*(\d{1,2})\b|"
    r"\b(\d{1,2})(?:st|nd|rd|th|[ª°a])?\s*(?:edizione|edition)\b|"
    r"\b(\d{1,2}\.\d+)\b", re.I,
)
_PUBLICATION_DATE_SOURCES = {"publication", "published", "published_at", "article", "article_published", "unknown", "deadline"}


def _get(event: EventLike, key: str, default: Any = "") -> Any:
    return event.get(key, default) if isinstance(event, Mapping) else getattr(event, key, default)


def title_core_words(text: str) -> list[str]:
    return [word for word in re.findall(r"[^\W_]+", (text or "").lower())
            if len(word) >= 2 and not word.isdigit() and word not in _GENERIC]


def distinctive_keywords(text: str) -> set[str]:
    return set(title_core_words(text))


def _identity_words(text: str) -> list[str]:
    return [word for word in re.findall(r"[^\W_]+", (text or "").lower())
            if len(word) >= 2 and not word.isdigit() and (word not in _GENERIC or word in _TOPICS)]


def _event_date(event: EventLike):
    if _get(event, "date_source") in _PUBLICATION_DATE_SOURCES:
        return None
    return HackathonEvent(title="", url="", source="", date_str=_get(event, "date_str")).parsed_date()


def _edition_years(event: EventLike) -> set[str]:
    # Do not infer edition from publication timestamps or years in a recap body.
    years = set(_YEAR.findall(_get(event, "title")))
    if years:
        return years
    date = _event_date(event)
    if date:
        return {str(date.year)}
    return set(_YEAR.findall(_get(event, "url")))


def editions_compatible(left: EventLike, right: EventLike) -> bool:
    left_date, right_date = _event_date(left), _event_date(right)
    if left_date and right_date and left_date != right_date:
        return False
    left_years, right_years = _edition_years(left), _edition_years(right)
    if left_years and right_years and left_years.isdisjoint(right_years):
        return False
    left_editions = {next(x for x in match if x) for match in _EDITION.findall(_get(left, "title"))}
    right_editions = {next(x for x in match if x) for match in _EDITION.findall(_get(right, "title"))}
    return not (left_editions and right_editions and left_editions.isdisjoint(right_editions))


# Listing and recommendation parameters Meetup appends to one event page.
_MEETUP_TRACKING_PARAMS = frozenset({"recid", "recsource", "searchid", "eventorigin"})
_MEETUP_EVENT_PATH = re.compile(r"/events/(\d+)(?:/|$)")
_MEETUP_LOCALE_PREFIX = re.compile(r"^/[a-z]{2}-[a-z]{2}(?=/|$)", re.I)


def _is_meetup(netloc: str) -> bool:
    return netloc.removeprefix("www.") == "meetup.com"


def _identity_url(url: str) -> str:
    """Compare URLs without changing the stored URL or the ID derived from it."""
    parsed = urlsplit(_normalize_url(url))
    if parsed.netloc in {"lu.ma", "www.lu.ma", "www.luma.com"}:
        return urlunsplit(("https", "luma.com", parsed.path, parsed.query, ""))
    if _is_meetup(parsed.netloc):
        # The event number names one event under any host, locale, group slug or listing.
        event_id = _MEETUP_EVENT_PATH.search(parsed.path)
        if event_id:
            return f"https://www.meetup.com/events/{event_id.group(1)}"
        query = urlencode([(key, value) for key, value in parse_qsl(parsed.query)
                           if key.lower() not in _MEETUP_TRACKING_PARAMS])
        path = _MEETUP_LOCALE_PREFIX.sub("", parsed.path)
        return urlunsplit(("https", "www.meetup.com", path, query, ""))
    return urlunsplit(parsed)


def _meetup_event_id(url: str) -> str | None:
    """Meetup event number, which names exactly one event, including localized paths."""
    parsed = urlsplit(_normalize_url(url))
    if not _is_meetup(parsed.netloc):
        return None
    match = _MEETUP_EVENT_PATH.search(parsed.path)
    return match.group(1) if match else None


def _distinct_meetup_events(left: EventLike, right: EventLike) -> bool:
    left_id, right_id = _meetup_event_id(_get(left, "url")), _meetup_event_id(_get(right, "url"))
    return bool(left_id and right_id and left_id != right_id)


def alternate_url_list(primary_url: str, urls) -> list[str]:
    """Normalized aliases of the primary URL.

    Meetup listing parameters create a new URL for every appearance of an event:
    keep one alias per Meetup event number, none for the primary's own number,
    and never a different Meetup event than the primary one.
    """
    primary = _normalize_url(primary_url)
    primary_meetup = _meetup_event_id(primary_url)
    aliases: list[str] = []
    meetup_seen: set[str] = set()
    for url in sorted({_normalize_url(url) for url in urls if url} - {primary}):
        meetup = _meetup_event_id(url)
        if meetup:
            if meetup in meetup_seen or (primary_meetup and meetup != primary_meetup) or meetup == primary_meetup:
                continue
            meetup_seen.add(meetup)
        aliases.append(url)
    return aliases


def prune_unrelated_alternate_urls(record: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Repair aliases attached by the pre-2026-10-11 matcher, which linked unrelated pages.

    That matcher accepted shared fragments such as "11 00 am" or "in to your" as
    identity, so archived aliases include login pages and foreign Meetup events.
    Every alias acts as an identity key, so a stale one silently discards new
    candidates. One-off repair, not a per-scan rule: a valid alias may be a short
    ID (luma.com/abc123) that this keyword test would reject.

    Kept: aliases whose host or path names a distinctive word of the title.
    Dropped: Meetup events other than the primary one, and every other alias.
    """
    repaired = _record(record)
    primary = repaired.get("url", "")
    keywords = {word for word in distinctive_keywords(repaired.get("title", "")) if len(word) >= 3}
    kept: list[str] = []
    for url in alternate_url_list(primary, repaired.get("alternate_urls", [])):
        parsed = urlsplit(url)
        tokens = set(re.findall(r"[^\W_]+", f"{parsed.netloc} {unquote(parsed.path)}".lower()))
        if _meetup_event_id(url) and _meetup_event_id(url) != _meetup_event_id(primary):
            continue
        if keywords & tokens:
            kept.append(url)
    dropped = sorted(set(repaired.get("alternate_urls", [])) - set(kept))
    repaired["alternate_urls"] = kept
    return repaired, dropped


def _urls(event: EventLike) -> set[str]:
    return {_identity_url(url) for url in [_get(event, "url"), *_get(event, "alternate_urls", [])]
            if isinstance(url, str) and url.strip()}


def same_event(left: EventLike, right: EventLike) -> bool:
    """Match event identity, rejecting incompatible dates/editions even on one URL."""
    if not editions_compatible(left, right):
        return False
    # Two Meetup event numbers are two events, even if a stale alias links them.
    if _distinct_meetup_events(left, right):
        return False
    if _urls(left) & _urls(right):
        return True
    left_title, right_title = _get(left, "title"), _get(right, "title")
    left_core, right_core = distinctive_keywords(left_title), distinctive_keywords(right_title)
    common = left_core & right_core
    if not common:
        return False
    ratio = SequenceMatcher(None, _normalize_title(left_title), _normalize_title(right_title)).ratio()
    # Generic prefixes must not dominate the fuzzy score (e.g. "Hackathon ...").
    core_ratio = SequenceMatcher(None, " ".join(_identity_words(left_title)),
                                " ".join(_identity_words(right_title))).ratio()
    shared_identity = len(common) / min(len(left_core), len(right_core))
    if (ratio >= config.FUZZY_DEDUP_THRESHOLD
            and core_ratio >= config.FUZZY_DEDUP_THRESHOLD
            and shared_identity >= config.FUZZY_DEDUP_THRESHOLD):
        return True
    left_date, right_date = _event_date(left), _event_date(right)
    if not left_date or left_date != right_date:
        return False
    # Same date and a contained distinctive title: e.g. Wikimedia and a named recap.
    left_identity, right_identity = set(_identity_words(left_title)), set(_identity_words(right_title))
    if left_identity <= right_identity or right_identity <= left_identity:
        return True
    # Cross-reference requires a real ordered phrase, not arbitrary shared words.
    for title, other in ((left_title, right), (right_title, left)):
        phrase = title_core_words(title)
        if len(phrase) < 3:
            continue
        text = title_core_words(_get(other, "title") + " " + _get(other, "description"))
        if any(text[index:index + len(phrase)] == phrase for index in range(len(text) - len(phrase) + 1)):
            return True
    return False


def _record(event: EventLike) -> dict[str, Any]:
    return deepcopy(dict(event) if isinstance(event, Mapping) else event.to_dict())


def _quality(record: Mapping[str, Any]) -> tuple:
    status = record.get("review_status", "")
    reviewed = 2 if status in {"manual_approved", "approved"} else int(status == "ai_verified")
    # A publication date is not evidence of the event schedule.
    event_date = _event_date(record)
    date_source = record.get("date_source", "")
    date_evidence = int(bool(event_date) and date_source in {"event", "event_jsonld", "event_card", "event_api", "structured", "event_structured", "manual", "source"})
    direct = int(record.get("source", "") not in {"web_search", ""})
    url = record.get("url", "")
    editorial = int("lists." not in url and "hyperkitty" not in url)
    return (reviewed, date_evidence, editorial, direct, bool(event_date),
            bool(record.get("location")), min(len(record.get("description", "")), 2000),
            len(distinctive_keywords(record.get("title", ""))))


def _rank_key(record: Mapping[str, Any]) -> tuple:
    # Ascending key, strongest record first; final lexical keys break every tie.
    return (*(-int(value) for value in _quality(record)),
            _normalize_url(record.get("url", "")), record.get("source", ""),
            record.get("title", ""), record.get("date_str", ""),
            record.get("description", ""), record.get("location", ""), record.get("organizer", ""),
            json.dumps(dict(record), sort_keys=True, ensure_ascii=False, default=str))


def merge_event_evidence(left: EventLike, right: EventLike) -> dict[str, Any]:
    """Copy the better record; fill missing fields only, never combine conflicting facts.

    The return type is always a dict, preserving extra review/provenance fields.
    Incompatible editions at the same URL select one complete record (newest
    explicit edition) because the existing URL-based ID cannot store both.
    """
    records = [_record(left), _record(right)]
    if not editions_compatible(left, right):
        if _identity_url(_get(left, "url")) != _identity_url(_get(right, "url")):
            raise ValueError("Cannot merge incompatible event editions")
        logger.warning("Conflicting editions reuse one URL; preserving one record without mixing facts: %s", _get(left, "url"))
        def edition_key(record):
            date = _event_date(record)
            years = _edition_years(record)
            versions = [float(next(value for value in match if value))
                        for match in _EDITION.findall(record.get("title", ""))]
            return (max(years) if years else "", date.isoformat() if date else "", max(versions, default=0))
        latest = max(edition_key(record) for record in records)
        return sorted((record for record in records if edition_key(record) == latest), key=_rank_key)[0]
    if not same_event(left, right):
        raise ValueError("Cannot merge unrelated events")
    primary, secondary = sorted(records, key=_rank_key)
    for name in ("description", "location", "organizer", "published_at"):
        if not primary.get(name) and secondary.get(name):
            primary[name] = secondary[name]
    if not primary.get("date_str") and secondary.get("date_str"):
        primary["date_str"] = secondary["date_str"]
        primary["date_source"] = secondary.get("date_source", "")
    urls = [url for record in records for url in [record.get("url", ""), *record.get("alternate_urls", [])]]
    primary["alternate_urls"] = alternate_url_list(primary.get("url", ""), urls)
    timestamps = [record.get("discovered_at") for record in records if record.get("discovered_at")]
    if timestamps:
        primary["discovered_at"] = min(timestamps)
    return primary


def deduplicate_event_dicts(events: list[dict]) -> list[dict]:
    """Deterministic consolidation, retaining incompatible editions on distinct URLs."""
    by_url: dict[str, dict] = {}
    for event in sorted(events, key=_rank_key):
        url = _identity_url(event.get("url", ""))
        if url in by_url:
            by_url[url] = merge_event_evidence(by_url[url], event)
        else:
            by_url[url] = _record(event)
    unique: list[dict] = []
    for event in sorted(by_url.values(), key=_rank_key):
        match = next((index for index, kept in enumerate(unique) if same_event(event, kept)), None)
        if match is None:
            unique.append(event)
        else:
            unique[match] = merge_event_evidence(unique[match], event)
    return sorted(unique, key=lambda record: (_normalize_url(record.get("url", "")), record.get("date_str", "")))


def deduplicate_events(events: list[HackathonEvent]) -> list[HackathonEvent]:
    allowed = {field.name for field in fields(HackathonEvent)}
    return [HackathonEvent(**{key: value for key, value in record.items() if key in allowed})
            for record in deduplicate_event_dicts([event.to_dict() for event in events])]
