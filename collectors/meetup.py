"""
Collector Meetup — ricerca eventi hackathon/tech a Milano via GraphQL API.

Meetup ha un'API GraphQL pubblica (non autenticata per ricerca base).
Se configurato MEETUP_API_KEY, la usa per query autenticate con risultati migliori.
Altrimenti, scraping HTML della pagina di ricerca come fallback.
"""

import json
import logging

from bs4 import BeautifulSoup

import config
from models import BaseCollector, HackathonEvent
from utils.http import safe_get, safe_get_json

logger = logging.getLogger(__name__)

# Endpoint GraphQL pubblico
MEETUP_GQL_URL = "https://www.meetup.com/gql"

# Pagine di ricerca (fallback scraping)
MEETUP_SEARCH_URLS = [
    "https://www.meetup.com/find/?keywords=hackathon&location=Milan%2C+Italy&source=EVENTS",
    "https://www.meetup.com/find/?keywords=coding+challenge&location=Milan%2C+Italy&source=EVENTS",
    "https://www.meetup.com/find/?keywords=hack&location=Milano&source=EVENTS",
]

# Query GraphQL per cercare eventi
SEARCH_QUERY = """
query ($filter: SearchConnectionFilter!) {
  searchConnection(filter: $filter, first: 20) {
    edges {
      node {
        ... on Event {
          id
          title
          eventUrl
          description
          dateTime
          venue {
            name
            address
            city
          }
          group {
            name
          }
        }
      }
    }
  }
}
"""

SEARCH_KEYWORDS = [
    "hackathon",
    "coding challenge",
    "hack",
    "makeathon",
    "buildathon",
]


class MeetupCollector(BaseCollector):

    @property
    def name(self) -> str:
        return "meetup"

    def collect(self) -> list[HackathonEvent]:
        # Try GraphQL API first
        events = self._collect_graphql()
        if events:
            logger.info("Meetup: trovati %d eventi via GraphQL", len(events))
            return events

        # Fallback: HTML scraping
        events = self._collect_html()
        logger.info("Meetup: trovati %d eventi via HTML scraping", len(events))
        return events

    def _collect_graphql(self) -> list[HackathonEvent]:
        """Cerca eventi tramite l'API GraphQL di Meetup."""
        all_events: list[HackathonEvent] = []
        seen_urls: set[str] = set()

        for keyword in SEARCH_KEYWORDS:
            variables = {
                "filter": {
                    "query": keyword,
                    "lat": 45.4642,
                    "lon": 9.1900,
                    "radius": config.SEARCH_RADIUS_KM,
                    "source": "EVENTS",
                    "eventType": "PHYSICAL",
                }
            }

            headers = {
                "Content-Type": "application/json",
            }
            if getattr(config, "MEETUP_API_KEY", ""):
                headers["Authorization"] = f"Bearer {config.MEETUP_API_KEY}"

            try:
                from utils.http import get_session
                session = get_session()
                resp = session.post(
                    MEETUP_GQL_URL,
                    json={"query": SEARCH_QUERY, "variables": variables},
                    headers=headers,
                    timeout=config.HTTP_TIMEOUT,
                )
                if resp.status_code >= 400:
                    logger.debug("Meetup GraphQL %d per keyword '%s'", resp.status_code, keyword)
                    continue

                data = resp.json()
            except Exception as e:
                logger.debug("Meetup GraphQL error: %s", e)
                continue

            edges = (
                data.get("data", {})
                .get("searchConnection", {})
                .get("edges", [])
            )

            for edge in edges:
                node = edge.get("node", {})
                if not node:
                    continue

                url = node.get("eventUrl", "")
                title = node.get("title", "")
                if not url or not title or url in seen_urls:
                    continue
                seen_urls.add(url)

                venue = node.get("venue", {}) or {}
                venue_parts = [venue.get("name", ""), venue.get("address", ""), venue.get("city", "")]
                location = ", ".join(p for p in venue_parts if p)

                group = node.get("group", {}) or {}

                all_events.append(HackathonEvent(
                    title=title,
                    url=url,
                    source=self.name,
                    description=(node.get("description", "") or "")[:500],
                    date_str=node.get("dateTime", ""),
                    location=location,
                    organizer=group.get("name", ""),
                ))

        return all_events

    def _collect_html(self) -> list[HackathonEvent]:
        """Fallback: scraping delle pagine di ricerca Meetup."""
        all_events: list[HackathonEvent] = []
        seen_urls: set[str] = set()

        for url in MEETUP_SEARCH_URLS:
            response = safe_get(url)
            if response is None:
                continue

            events = self._parse_search_html(response.text, seen_urls)
            all_events.extend(events)

        return all_events

    def _parse_search_html(self, html: str, seen_urls: set[str]) -> list[HackathonEvent]:
        """Parsa la pagina di ricerca Meetup."""
        soup = BeautifulSoup(html, "lxml")
        events: list[HackathonEvent] = []

        # Meetup usa __NEXT_DATA__ (Next.js)
        script = soup.find("script", id="__NEXT_DATA__")
        if script:
            try:
                data = json.loads(script.string)
                results = (
                    data.get("props", {})
                    .get("pageProps", {})
                    .get("searchResults", {})
                    .get("edges", [])
                )
                for edge in results:
                    node = edge.get("node", {}).get("result", {})
                    url = node.get("eventUrl", "") or node.get("link", "")
                    title = node.get("title", "")
                    if not url or not title or url in seen_urls:
                        continue
                    if not url.startswith("http"):
                        url = f"https://www.meetup.com{url}"
                    seen_urls.add(url)

                    venue = node.get("venue", {}) or {}
                    group = node.get("group", {}) or {}
                    events.append(HackathonEvent(
                        title=title,
                        url=url,
                        source=self.name,
                        description=(node.get("description", "") or "")[:500],
                        date_str=node.get("dateTime", ""),
                        location=venue.get("city", "") if venue else "",
                        organizer=group.get("name", "") if isinstance(group, dict) else "",
                    ))
            except (json.JSONDecodeError, KeyError) as e:
                logger.debug("Meetup __NEXT_DATA__ parse error: %s", e)

        # Fallback: cerca link a eventi
        if not events:
            links = soup.find_all("a", href=lambda h: h and "/events/" in h and "meetup.com" in h)
            for link in links:
                href = link.get("href", "")
                title = link.get_text(strip=True)
                if not href or not title or href in seen_urls:
                    continue
                if not href.startswith("http"):
                    href = f"https://www.meetup.com{href}"
                seen_urls.add(href)

                events.append(HackathonEvent(
                    title=title,
                    url=href,
                    source=self.name,
                    location="",
                ))

        return events
