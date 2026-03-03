"""
Storage JSON con deduplicazione a tre livelli.

Livello 1 — Esatto: SHA256(normalized_url) — stesso URL = stesso evento.
Livello 2 — Fuzzy:  SequenceMatcher sul titolo normalizzato (ratio > 0.75)
                     → stesso evento da fonti diverse con URL differenti.
Livello 3 — Semantico: stessa data + keyword distintive condivise tra
                        titolo/descrizione → stesso evento con titoli diversi
                        (es. pagina ufficiale vs articolo/post che lo cita).
"""

import json
import logging
import re
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

    # ─── Keyword distintive per dedup semantico ─────────────────────────

    # Parole troppo generiche per essere usate come keyword di dedup
    _STOPWORDS = frozenset({
        # Italiano
        "del", "dei", "delle", "degli", "per", "con", "una", "uno", "alla",
        "alle", "allo", "agli", "che", "nel", "nella", "sono", "come", "dal",
        "dalla", "anche", "tra", "più", "suo", "suoi", "loro", "questo",
        "questa", "essere", "fare", "dire", "non", "tutto", "tutti",
        # Inglese
        "the", "for", "and", "with", "from", "that", "this", "will", "have",
        "has", "are", "was", "were", "been", "being", "about", "into",
        "your", "our", "their", "which", "what", "when", "where", "how",
        # Termini evento generici (non discriminanti)
        "hackathon", "challenge", "event", "evento", "eventi", "competition",
        "milano", "milan", "italy", "italia", "lombardia",
        "università", "university", "politecnico",
        "progetti", "iniziative", "open", "innovation", "innovazione",
        "2024", "2025", "2026", "2027", "2028",
    })

    @staticmethod
    def _extract_distinctive_keywords(text: str) -> set[str]:
        """Estrae keyword distintive da un testo (titolo + descrizione).

        Restituisce token significativi: acronimi (>=2 char MAIUSCOLI nel
        testo originale) e parole ≥ 4 caratteri non nella stopword list.
        """
        if not text:
            return set()
        # Estrai acronimi dal testo originale (prima della normalizzazione)
        acronyms = {m.lower() for m in re.findall(r"\b[A-Z]{2,}\b", text)}
        # Normalizza e tokenizza
        norm = re.sub(r"[^\w\s]", " ", text.lower())
        words = set(norm.split())
        # Tieni parole ≥ 4 char + acronimi ≥ 2 char, escluse stopwords
        keywords = {w for w in words if len(w) >= 4 and w not in EventStore._STOPWORDS}
        keywords |= {a for a in acronyms if len(a) >= 2 and a not in EventStore._STOPWORDS}
        return keywords

    @staticmethod
    def _parse_date_prefix(date_str: str) -> str:
        """Estrae YYYY-MM-DD dal campo date_str (può contenere timestamp ISO)."""
        if not date_str:
            return ""
        return date_str[:10] if len(date_str) >= 10 else ""

    def find_same_event_by_date_keywords(self, event: HackathonEvent) -> dict | None:
        """Livello 3: stessa data + keyword distintive condivise.

        Per eventi con la stessa data (non vuota), controlla se keyword
        distintive del nuovo evento appaiono nel titolo+descrizione di
        un evento nello storico (o viceversa).
        Match se overlap ≥ 2 keyword, oppure 1 keyword molto lunga (≥8 char).

        Returns:
            Il dict dell'evento matchato, o None.
        """
        event_date = self._parse_date_prefix(event.date_str)
        if not event_date:
            return None

        event_text = f"{event.title} {event.description}"
        event_kw = self._extract_distinctive_keywords(event_text)
        if len(event_kw) < 2:
            return None

        for stored in self._events.values():
            stored_date = self._parse_date_prefix(stored.get("date_str", ""))
            if stored_date != event_date:
                continue

            stored_text = f"{stored.get('title', '')} {stored.get('description', '')}"
            stored_kw = self._extract_distinctive_keywords(stored_text)

            overlap = event_kw & stored_kw
            # ≥2 keyword qualsiasi, OPPURE 1 keyword molto distintiva (≥8 char)
            # es. "wikimedia" (9 char) è sufficiente da sola come segnale forte
            has_strong_kw = any(len(kw) >= 8 for kw in overlap)
            if len(overlap) >= 2 or (len(overlap) == 1 and has_strong_kw):
                logger.debug(
                    "Date+keyword match: '%s' ≈ '%s' (date=%s, overlap=%s)",
                    event.title[:60], stored.get("title", "")[:60],
                    event_date, overlap,
                )
                return stored

        return None

    def is_duplicate(self, event: HackathonEvent) -> bool:
        """Verifica se un evento è duplicato (livello 1 + 2 + 3).

        Se è un duplicato fuzzy o semantico (stesso evento, URL diverso),
        aggiunge l'URL come alternate_url all'evento esistente.

        Returns:
            True se l'evento è duplicato, False se è nuovo.
        """
        # Livello 1a: URL esatto (ID = hash dell'URL)
        if self.has_event(event.id):
            return True

        # Livello 1b: URL già noto come alternate_url di un evento esistente
        if event.url in self._alt_url_index:
            return True

        # Livello 2: titolo fuzzy
        match = self.find_fuzzy_match(event.title_normalized)
        if match is not None:
            self._add_alternate_url(match, event, "Fuzzy match")
            return True

        # Livello 3: stessa data + keyword distintive
        match = self.find_same_event_by_date_keywords(event)
        if match is not None:
            self._add_alternate_url(match, event, "Date+keyword match")
            return True

        return False

    def _add_alternate_url(self, match: dict, event: HackathonEvent, label: str) -> None:
        """Aggiunge l'URL di un evento duplicato come alternate_url e aggiorna l'indice."""
        alt_urls = match.setdefault("alternate_urls", [])
        if event.url not in alt_urls:
            alt_urls.append(event.url)
            # Aggiorna l'indice alternate_urls
            self._alt_url_index[event.url] = match.get("id", "")
            logger.info(
                "%s: '%s' ≈ '%s' — aggiunta URL alternativa",
                label, event.title, match.get("title"),
            )

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
