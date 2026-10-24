"""Edition-specific exclusions verified from event pages or manual reports.

Keep these rules shared by ingestion and stored-event cleanup. Match parsed URL
components so tracking parameters and host aliases cannot revive an excluded
event, while other editions and registration IDs remain eligible.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote, urlsplit


_HARVARD_PATHS = {
    "/knowledge/harvard-hsil-hackathon-2026",
    "/en/knowledge/harvard-hsil-hackathon-2026",
}
_MILAN_AI_WEEK_PATH = "/ai-hackathons/milan-ai-week-hackathon"
_GDG_PATH = (
    "/events/details/google-gdg-on-campus-polytechnic-university-of-milan-"
    "presents-gdg-ai-hack-2026"
)
_POLIMI_CONFERENCE_PATH = (
    "/il-politecnico/eventi/dettaglio-evento/innovation-challenge-2026-"
    "soluzioni-per-evitare-la-disillusione-dellai"
)
_BCG_CANDIDATE_PATHS = {
    "/events/candidate/landing",
    "/events/candidate/registration",
}
_AI_OLYMPICS_EVENTBRITE_PATH = re.compile(r"/e/(?:[^/]*-)?1987936520647")
_BAINSA_INSTAGRAM_POSTS = {"/p/ddw5fhmkp63", "/p/ddzilhliqvc"}
_BAINSA_LINKEDIN_ACTIVITY = re.compile(r"(?:^|[-:])7506341576797929472(?:-|$)")
# Meetup localizes paths (/it-IT/...): match the group and event number only.
_MASTER_THE_VIBE_CHRISTMAS = re.compile(r"(?:^|/)master-the-vibe-milan/events/315691626$")
_GLAM_TOOL_HOSPITAL_PATH = "/wiki/glam_tool_hospital/wikimedia_hackathon,_milan_2026"


# Pages excluded only because they duplicate an official page: the event is valid.
_BCG_DUPLICATE = "duplicato noto (pagina ufficiale: bcgplatinion.com/hackathon)"
_DUPLICATE_PAGE_REASONS = frozenset({_BCG_DUPLICATE})


def alias_exclusion_reason(url: str) -> str | None:
    """Exclusion that still applies when the page is only an alias of a stored event.

    An excluded event (past, conference, not a hackathon) stays excluded under
    any alias. A duplicate page is expected among the aliases of the event it
    duplicates, and must not remove that event.
    """
    reason = event_exclusion_reason(url)
    return None if reason in _DUPLICATE_PAGE_REASONS else reason


def event_exclusion_reason(url: str) -> str | None:
    """Return the reason for a known exclusion, independent of extracted dates."""
    try:
        parsed = urlsplit((url or "").strip())
        host = (parsed.hostname or "").lower().removeprefix("www.")
        path = unquote(parsed.path).rstrip("/").lower()
    except ValueError:
        return None

    # BAINSA/Anthropic accessibility edition, 26 September 2026. These posts
    # announce the same finished event; do not block the organizer or new posts.
    if (
        host == "instagram.com" and path in _BAINSA_INSTAGRAM_POSTS
        or (host == "linkedin.com" or host.endswith(".linkedin.com"))
        and path.startswith(("/posts/", "/feed/update/"))
        and _BAINSA_LINKEDIN_ACTIVITY.search(path)
    ):
        return "evento passato noto (BAINSA Accessibility Hackathon, 26 settembre 2026)"

    # Harvard HSIL: 10–11 April 2026. GDG AI HACK: 8–10 May 2026.
    if host == "gsom.polimi.it" and path in _HARVARD_PATHS:
        return "evento passato noto (Harvard HSIL, 10–11 aprile 2026)"
    if host == "gdg.community.dev" and path == _GDG_PATH:
        return "evento passato noto (GDG AI HACK, 8–10 maggio 2026)"

    # These are aliases and project subpages of AI Agent Olympics, 19–20 May 2026.
    if (
        host in {"lu.ma", "luma.com"} and path == "/5fxlxfl5"
        or host == "lablab.ai" and (
            path == _MILAN_AI_WEEK_PATH or path.startswith(_MILAN_AI_WEEK_PATH + "/")
        )
        or host in {"eventbrite.com", "eventbrite.it"}
        and _AI_OLYMPICS_EVENTBRITE_PATH.fullmatch(path)
    ):
        return "evento passato noto (AI Agent Olympics, 19–20 maggio 2026)"

    if host in {"bcg.eightfold.ai", "experiencedtalent.bcg.com"} and path in _BCG_CANDIDATE_PATHS:
        event_ids = parse_qs(parsed.query).get("plannedEventId", [])
        if "aQnm026Vg" in event_ids:
            return _BCG_DUPLICATE

    # The official 21 September 2026 page labels this event as "Convegni".
    if host == "polimi.it" and path == _POLIMI_CONFERENCE_PATH:
        return "convegno, non hackathon (Innovation Challenge 2026)"

    # "Hackathon di Natale!" (3 December 2026): its agenda is a talk, Q&A and pizza.
    if host == "meetup.com" and _MASTER_THE_VIBE_CHRISTMAS.search(path):
        return "meetup con talk, non hackathon (Hackathon di Natale!, 3 dicembre 2026)"

    # Project page of a session at the Wikimedia Hackathon, 1–3 May 2026.
    if host == "meta.wikimedia.org" and (
        path == _GLAM_TOOL_HOSPITAL_PATH or path.startswith(_GLAM_TOOL_HOSPITAL_PATH + "/")
    ):
        return "pagina di progetto di un evento passato (Wikimedia Hackathon, 1–3 maggio 2026)"

    return None
