"""
Collector Luma — estrazione eventi da lu.ma/milan.

Strategia primaria: fetch HTML ed estrazione JSON da tag <script id="__NEXT_DATA__">.
Luma è costruito su Next.js, quindi i dati degli eventi sono pre-renderizzati
nel tag __NEXT_DATA__ come JSON, senza necessità di rendering JS.

Se __NEXT_DATA__ non è trovato (migrazione architettura), il collector
logga un warning e ritorna lista vuota (fallback Playwright documentato nel README).
"""

import json
import logging
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

import config
from models import BaseCollector, HackathonEvent
from utils.http import safe_get
from utils.collector_health import record_issue

logger = logging.getLogger(__name__)

LUMA_MILAN_URL = "https://luma.com/milan"


class LumaCollector(BaseCollector):

    @property
    def name(self) -> str:
        return "luma"

    def collect(self) -> list[HackathonEvent]:
        response = safe_get(LUMA_MILAN_URL)
        if response is None:
            logger.error("Luma: impossibile raggiungere %s", LUMA_MILAN_URL)
            return []

        # Strategia 1: __NEXT_DATA__
        events = self._extract_from_next_data(response.text)
        if events is not None:
            logger.info("Luma: trovati %d eventi via __NEXT_DATA__", len(events))
            return events

        # Strategia 2: parsing HTML grezzo
        events = self._extract_from_html(response.text)
        if events:
            logger.info("Luma: trovati %d eventi via HTML fallback", len(events))
            return events

        logger.warning(
            "Luma: nessun dato estratto. Il sito potrebbe aver cambiato struttura. "
            "Considerare l'implementazione del fallback Playwright."
        )
        record_issue("parse_error", "Luma event structure not recognized", url=LUMA_MILAN_URL)
        return []

    def _extract_from_next_data(self, html: str) -> list[HackathonEvent] | None:
        """Estrae eventi dal tag <script id='__NEXT_DATA__'>."""
        soup = BeautifulSoup(html, "lxml")
        script_tag = soup.find("script", id="__NEXT_DATA__")

        if not script_tag or not script_tag.string:
            logger.info("Luma: tag __NEXT_DATA__ non trovato, provo HTML fallback")
            return None

        try:
            data = json.loads(script_tag.string)
        except json.JSONDecodeError as e:
            logger.warning("Luma: JSON non valido in __NEXT_DATA__: %s", e)
            return None

        # Naviga la struttura Next.js per trovare gli eventi
        # La struttura tipica è: props.pageProps.events o simile
        events_data = self._find_events_in_json(data)
        if events_data is None:
            logger.info("Luma: nessun evento trovato nella struttura __NEXT_DATA__")
            return None

        events: list[HackathonEvent] = []
        for raw in events_data:
            event = self._parse_luma_event(raw)
            if event:
                events.append(event)

        return events

    def _find_events_in_json(self, data: dict) -> list | None:
        """Cerca ricorsivamente la lista di eventi nella struttura JSON di Next.js."""
        # Prova percorsi noti
        try:
            # Percorso comune in Luma
            page_props = data.get("props", {}).get("pageProps", {})

            # Cerca in vari posti dove Luma potrebbe mettere gli eventi
            for key in ["events", "initialEvents", "featuredEvents", "data"]:
                if key in page_props:
                    candidate = page_props[key]
                    if isinstance(candidate, list) and (not candidate or self._looks_like_events(candidate)):
                        return candidate
                    if isinstance(candidate, dict):
                        # Potrebbe essere paginato
                        for subkey in ["events", "items", "results", "nodes"]:
                            values = candidate.get(subkey)
                            if isinstance(values, list) and (not values or self._looks_like_events(values)):
                                return values

            # Cerca ricorsivamente qualsiasi lista con oggetti che sembrano eventi
            return self._deep_find_events(data)

        except (KeyError, TypeError, AttributeError):
            return None

    def _deep_find_events(self, obj, depth: int = 0) -> list | None:
        """Cerca ricorsivamente una lista di oggetti evento-like."""
        if depth > 6:  # Limita la profondità
            return None

        if isinstance(obj, list) and self._looks_like_events(obj):
            return obj

        if isinstance(obj, dict):
            for key, value in obj.items():
                if key in {"events", "initialEvents", "featuredEvents"} and value == []:
                    return []
                result = self._deep_find_events(value, depth + 1)
                if result is not None:
                    return result

        return None

    @staticmethod
    def _looks_like_events(items: list) -> bool:
        if not items or not isinstance(items[0], dict):
            return False
        first = items[0]
        if isinstance(first.get("event"), dict):
            return True
        return (
            any(key in first for key in ("name", "title", "event_name"))
            and any(key in first for key in ("start_at", "start_date", "geo_address_info"))
        )

    def _parse_luma_event(self, raw: dict) -> HackathonEvent | None:
        """Converte un evento Luma raw in HackathonEvent."""
        try:
            # Luma può avere la struttura annidata: raw potrebbe avere un campo "event"
            event_data = raw.get("event", raw)

            title = (
                event_data.get("name", "")
                or event_data.get("title", "")
                or event_data.get("event_name", "")
            ).strip()

            if not title:
                return None

            # URL: costruisci dall'ID o slug
            slug = event_data.get("url", "") or event_data.get("slug", "")
            api_id = event_data.get("api_id", "") or event_data.get("id", "")

            if slug:
                url = urljoin("https://lu.ma/", slug)
            elif api_id:
                url = f"https://lu.ma/{api_id}"
            else:
                url = LUMA_MILAN_URL

            description = event_data.get("description", "") or ""
            description = description[:500]

            # Date
            date_str = event_data.get("start_at", "") or event_data.get("start_date", "") or ""
            end_date = event_data.get("end_at", "") or event_data.get("end_date", "") or ""
            if end_date and date_str:
                date_str = f"{date_str} — {end_date}"

            # Location
            location = ""
            geo = event_data.get("geo_address_info", {}) or {}
            if geo:
                location = geo.get("full_address", "") or geo.get("city", "") or geo.get("city_state", "")

            return HackathonEvent(
                title=title,
                url=url,
                source=self.name,
                description=description,
                date_str=date_str,
                date_source="event_api" if date_str else "",
                location=location,
            )

        except Exception as e:
            logger.debug("Errore parsing evento Luma: %s", e)
            return None

    def _extract_from_html(self, html: str) -> list[HackathonEvent]:
        """Fallback: estrae eventi dal HTML puro (quando __NEXT_DATA__ non è disponibile)."""
        soup = BeautifulSoup(html, "lxml")
        events: list[HackathonEvent] = []
        seen: set[str] = set()

        # Cerca link che puntano a eventi lu.ma/xxx
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            text = link.get_text(strip=True)

            if not text or len(text) < 5:
                continue

            # Link a singoli eventi Luma
            full_url = urljoin(LUMA_MILAN_URL, href)
            parsed = urlparse(full_url)
            if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"lu.ma", "www.lu.ma", "luma.com", "www.luma.com"}:
                continue

            if full_url in seen:
                continue
            seen.add(full_url)

            # Escludi link di navigazione
            skip_paths = ["/login", "/signup", "/settings", "/explore", "/create", "/pricing"]
            if parsed.path in {"", "/", "/milan"} or any(parsed.path.startswith(p) for p in skip_paths):
                continue

            events.append(HackathonEvent(
                title=text,
                url=full_url,
                source=self.name,
                location="",
            ))

        return events


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    collector = LumaCollector()
    events = collector.collect()
    for e in events[:10]:
        print(f"  [{e.source}] {e.title} — {e.url}")
    print(f"  ... totale: {len(events)}")
