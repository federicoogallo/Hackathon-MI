"""
Storage JSON con identità evento condivisa con la pipeline.

URL e titoli distintivi identificano duplicati soltanto quando date ed
edizioni sono compatibili. Le parole generiche non identificano un evento.
"""

import json
import logging
from pathlib import Path

import config
from models import HackathonEvent, _normalize_url
from utils.event_identity import (
    alternate_url_list, distinctive_keywords, merge_event_evidence, same_event, title_core_words,
)

logger = logging.getLogger(__name__)


class EventStore:
    """Gestisce il caricamento, salvataggio e deduplicazione degli eventi."""

    def __init__(self, path: Path | None = None):
        self.path = path or config.EVENTS_FILE
        self._events: dict[str, dict] = {}  # id → event dict
        self._alt_url_index: dict[str, str] = {}  # alternate_url → primary event id
        self._load()

    # ─── Persistenza ────────────────────────────────────────────────────

    def _load(self) -> None:
        """Carica lo storico da file. Se corrotto o assente, riparte da vuoto."""
        if not self.path.exists():
            logger.info("Storico non trovato, si parte da zero: %s", self.path)
            return

        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("Storico corrotto (%s), si riparte da zero: %s", e, self.path)
            return

        events_list = data.get("events", [])
        for item in events_list:
            eid = item.get("id")
            if eid:
                self._events[eid] = item
                # Indicizza alternate_urls per lookup veloce
                for alt_url in item.get("alternate_urls", []):
                    self._alt_url_index[alt_url] = eid

        logger.info("Caricati %d eventi dallo storico", len(self._events))

    def save(self) -> None:
        """Salva lo storico su file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "last_check": None,  # Verrà impostato dall'orchestratore
            "events": list(self._events.values()),
        }
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info("Salvati %d eventi nello storico", len(self._events))

    # ─── Query ──────────────────────────────────────────────────────────

    @property
    def count(self) -> int:
        return len(self._events)

    def all_events(self) -> list[dict]:
        """Ritorna tutti gli eventi come lista di dict."""
        return list(self._events.values())

    def has_event(self, event_id: str) -> bool:
        """Livello 1: check esatto per ID (hash URL)."""
        return event_id in self._events

    def find_fuzzy_match(self, title_normalized: str, event: HackathonEvent | None = None) -> dict | None:
        """Compatibility wrapper; callers with a record retain date/edition guards."""
        candidate = event or HackathonEvent(title=title_normalized, url="", source="")
        return self._find_identity_match(candidate)

    @staticmethod
    def _extract_distinctive_keywords(text: str) -> set[str]:
        return distinctive_keywords(text)

    @staticmethod
    def _extract_title_core_words(title: str) -> list[str]:
        return title_core_words(title)

    def _find_identity_match(self, event: HackathonEvent) -> dict | None:
        return next((stored for _, stored in sorted(self._events.items())
                     if same_event(event, stored)), None)

    def find_same_event_by_date_keywords(self, event: HackathonEvent) -> dict | None:
        """Use the shared identity policy, never arbitrary description keywords."""
        return self._find_identity_match(event)

    def find_cross_reference_match(self, event: HackathonEvent) -> dict | None:
        """Cross-references obey the same edition and identity checks as all dedup."""
        return self._find_identity_match(event)

    def is_duplicate(self, event: HackathonEvent) -> bool:
        """Check identity without letting titles or reused URLs collapse editions.

        An incompatible edition on a reused URL returns False so it undergoes
        classification instead of being silently discarded as already known.
        """
        match = self._find_identity_match(event)
        if match is None:
            return False
        self._add_alternate_url(match, event, "Identity match")
        return True

    def _add_alternate_url(self, match: dict, event: HackathonEvent, label: str) -> None:
        urls = [*match.get("alternate_urls", []), event.url, *event.alternate_urls]
        match["alternate_urls"] = alternate_url_list(match.get("url", ""), urls)
        for url in match["alternate_urls"]:
            self._alt_url_index[url] = match.get("id", "")

    # ─── Modifica ───────────────────────────────────────────────────────

    def add_event(self, event: HackathonEvent) -> None:
        """Aggiunge un evento allo storico (senza controllo duplicati)."""
        incoming = event.to_dict()
        existing = self._events.get(event.id)
        if existing is not None:
            incoming = merge_event_evidence(existing, incoming)
        self._events[event.id] = incoming
        for url in incoming.get("alternate_urls", []):
            self._alt_url_index[url] = event.id

    def replace_events(self, events: list[dict]) -> None:
        """Sostituisce completamente lo storico con una lista di eventi."""
        self._events = {}
        self._alt_url_index = {}
        for item in events:
            eid = item.get("id")
            if not eid:
                continue
            self._events[eid] = item
            for alt_url in item.get("alternate_urls", []):
                self._alt_url_index[alt_url] = eid

    def set_last_check(self, timestamp: str) -> None:
        """Imposta il timestamp dell'ultimo check (usato al salvataggio)."""
        # Salvato nel prossimo save()
        self._last_check = timestamp

    def save_with_timestamp(self, timestamp: str) -> None:
        """Salva con timestamp dell'ultimo check."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "last_check": timestamp,
            "events": list(self._events.values()),
        }
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info("Salvati %d eventi nello storico (check: %s)", len(self._events), timestamp)

    def touch_last_check(self, timestamp: str) -> None:
        """Aggiorna solo il timestamp dell'ultimo check, preservando gli eventi su disco."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data: dict
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                data = loaded if isinstance(loaded, dict) else {}
            except (json.JSONDecodeError, ValueError, OSError) as e:
                logger.warning("Impossibile aggiornare timestamp storico (%s): %s", e, self.path)
                data = {}
        else:
            data = {}

        data.setdefault("events", [])
        data["last_check"] = timestamp
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info("Aggiornato timestamp storico (check: %s)", timestamp)
