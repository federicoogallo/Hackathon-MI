"""
Storage JSON con deduplicazione a due livelli.

Livello 1 — Esatto: SHA256(normalized_url) — stesso URL = stesso evento.
Livello 2 — Fuzzy:  SequenceMatcher sul titolo normalizzato (ratio > 0.85)
                     → stesso evento da fonti diverse con URL differenti.
"""

import json
import logging
from difflib import SequenceMatcher
from pathlib import Path

import config
from models import HackathonEvent

logger = logging.getLogger(__name__)


class EventStore:
    """Gestisce il caricamento, salvataggio e deduplicazione degli eventi."""

    def __init__(self, path: Path | None = None):
        self.path = path or config.EVENTS_FILE
        self._events: dict[str, dict] = {}  # id → event dict
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

    def find_fuzzy_match(self, title_normalized: str) -> dict | None:
        """Livello 2: cerca un evento con titolo simile (ratio > threshold).

        Returns:
            Il dict dell'evento matchato, o None.
        """
        for stored in self._events.values():
            stored_title = stored.get("title", "")
            # Normalizza il titolo stored con la stessa logica
            from models import _normalize_title
            stored_norm = _normalize_title(stored_title)

            ratio = SequenceMatcher(None, title_normalized, stored_norm).ratio()
            if ratio >= config.FUZZY_DEDUP_THRESHOLD:
                return stored
        return None

    def is_duplicate(self, event: HackathonEvent) -> bool:
        """Verifica se un evento è duplicato (livello 1 + livello 2).

        Se è un duplicato fuzzy (stesso evento, URL diverso),
        aggiunge l'URL come alternate_url all'evento esistente.

        Returns:
            True se l'evento è duplicato, False se è nuovo.
        """
        # Livello 1: URL esatto
        if self.has_event(event.id):
            return True

        # Livello 2: titolo fuzzy
        match = self.find_fuzzy_match(event.title_normalized)
        if match is not None:
            # Aggiorna alternate_urls dell'evento esistente
            alt_urls = match.setdefault("alternate_urls", [])
            if event.url not in alt_urls:
                alt_urls.append(event.url)
                logger.info(
                    "Fuzzy match: '%s' ≈ '%s' — aggiunta URL alternativa",
                    event.title,
                    match.get("title"),
                )
            return True

        return False

    # ─── Modifica ───────────────────────────────────────────────────────

    def add_event(self, event: HackathonEvent) -> None:
        """Aggiunge un evento allo storico (senza controllo duplicati)."""
        self._events[event.id] = event.to_dict()

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
