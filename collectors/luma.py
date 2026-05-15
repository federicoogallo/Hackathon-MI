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

from bs4 import BeautifulSoup

import config
from models import BaseCollector, HackathonEvent
from utils.http import safe_get

logger = logging.getLogger(__name__)

LUMA_MILAN_URL = "https://lu.ma/milan"


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
            return []

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
                    if isinstance(candidate, list) and len(candidate) > 0:
                        return candidate
                    if isinstance(candidate, dict):
                        # Potrebbe essere paginato
                        for subkey in ["events", "items", "results", "nodes"]:
                            if subkey in candidate and isinstance(candidate[subkey], list):
                                return candidate[subkey]

            # Cerca ricorsivamente qualsiasi lista con oggetti che sembrano eventi
            return self._deep_find_events(data)

        except (KeyError, TypeError, AttributeError):
            return None

    def _deep_find_events(self, obj, depth: int = 0) -> list | None:
        """Cerca ricorsivamente una lista di oggetti evento-like."""
        if depth > 6:  # Limita la profondità
            return None

        if isinstance(obj, list) and len(obj) > 0:
            # Verifica se gli elementi sembrano eventi (hanno title/name e url/link)
            first = obj[0]
            if isinstance(first, dict):
                has_event_keys = any(
                    k in first for k in ("name", "title", "event_name", "event")
                )
                if has_event_keys:
                    return obj

        if isinstance(obj, dict):
            for value in obj.values():
                result = self._deep_find_events(value, depth + 1)
                if result:
                    return result

        return None

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
                url = f"https://lu.ma/{slug}" if not slug.startswith("http") else slug
            elif api_id:
                url = f"https://lu.ma/{api_id}"
            else:
                url = LUMA_MILAN_URL

            description = event_data.get("description", "") or ""
            description = description[:500]

            # Date
            date_str = event_data.get("start_at", "") or event_data.get("start_date", "") or ""
            end_date = event_data.get("end_at", "") or event_data.get("end_date", "") or ""
            if end_date:
                date_str = f"{date_str} — {end_date}"

            # Location
            location = ""
            geo = event_data.get("geo_address_info", {}) or {}
            if geo:
                location = geo.get("full_address", "") or geo.get("city", "")

            return HackathonEvent(
                title=title,
                url=url,
                source=self.name,
                description=description,
                date_str=date_str,
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
            if href.startswith("/") and href != "/" and not href.startswith("//"):
                full_url = f"https://lu.ma{href}"
            elif "lu.ma/" in href:
                full_url = href
            else:
                continue

            if full_url in seen:
                continue
            seen.add(full_url)

            # Escludi link di navigazione
            skip_paths = ["/login", "/signup", "/settings", "/explore", "/create", "/pricing"]
            if any(href.startswith(p) for p in skip_paths):
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
