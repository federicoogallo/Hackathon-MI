"""
Modello dati e interfaccia base per il progetto Hackathon Monitor.

Definisce:
- HackathonEvent: dataclass normalizzata per rappresentare un evento
- BaseCollector: classe astratta che ogni collector deve implementare
"""

from __future__ import annotations

import hashlib
import re
import string
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Any, Optional
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode


def _normalize_url(url: str) -> str:
    """Normalizza un URL per deduplicazione:
    - lowercase hostname
    - rimuove query params di tracking (utm_*, ref, fbclid, etc.)
    - rimuove trailing slash
    - rimuove fragment
    """
    try:
        parsed = urlparse(url.strip())
        # Lowercase scheme e hostname
        scheme = parsed.scheme.lower() or "https"
        netloc = parsed.netloc.lower()
        path = parsed.path.rstrip("/")

        # Filtra query params di tracking
        tracking_prefixes = ("utm_", "ref", "fbclid", "gclid", "mc_", "source")
        if parsed.query:
            params = parse_qs(parsed.query, keep_blank_values=False)
            filtered = {
                k: v
                for k, v in params.items()
                if not any(k.lower().startswith(tp) for tp in tracking_prefixes)
            }
            query = urlencode(filtered, doseq=True)
        else:
            query = ""

        return urlunparse((scheme, netloc, path, "", query, ""))
    except Exception:
        return url.strip().rstrip("/").lower()


def _normalize_title(title: str) -> str:
    """Normalizza un titolo per confronto fuzzy:
    - lowercase
    - rimuove punteggiatura
    - collassa spazi multipli
    """
    text = title.lower()
    text = text.translate(str.maketrans("", "", string.punctuation))
    text = re.sub(r"\s+", " ", text).strip()
    return text


@dataclass
class HackathonEvent:
    """Rappresentazione normalizzata di un evento hackathon."""

    title: str
    url: str
    source: str  # Nome del collector che ha trovato l'evento
    description: str = ""
    date_str: str = ""  # Data come stringa grezza (nessun parsing forzato)
    location: str = "Milano"
    organizer: str = ""
    is_hackathon: bool = False
    confidence: float = 0.0
    review_status: str = "ai_pending"
    review_reason: str = ""
    reviewed_at: str = ""
    alternate_urls: list[str] = field(default_factory=list)
    discovered_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def parsed_date(self) -> Optional[date]:
        """Prova a parsare `date_str` in un `date`.

        Supporta ISO, alcuni formati comuni e pattern numerici. Restituisce
        `None` se non è possibile interpretare la data.
        """
        s = (self.date_str or "").strip()
        if not s:
            return None

        # Prova ISO 8601
        try:
            return datetime.fromisoformat(s).date()
        except Exception:
            pass

        # Formati comuni
        fmts = [
            "%Y-%m-%d",
            "%d-%m-%Y",
            "%d/%m/%Y",
            "%d.%m.%Y",
            "%d %B %Y",
            "%d %b %Y",
            "%B %d, %Y",
            "%b %d, %Y",
        ]
        for f in fmts:
            try:
                return datetime.strptime(s, f).date()
            except Exception:
                continue

        # Cerca pattern YYYY-MM-DD
        m = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", s)
        if m:
            y, mth, d = m.groups()
            try:
                return date(int(y), int(mth), int(d))
            except Exception:
                pass

        # Cerca pattern DD/MM/YYYY o simili
        m = re.search(r"(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})", s)
        if m:
            d, mth, y = m.groups()
            try:
                y = int(y)
                if y < 100:
                    y += 2000
                return date(y, int(mth), int(d))
            except Exception:
                pass

        return None

    def is_past(self, ref_date: Optional[date] = None) -> bool:
        """Ritorna True se l'evento è strettamente precedente a `ref_date`.

        Se non è possibile determinare la data dell'evento restituisce False
        (non lo considera passato).
        """
        pd = self.parsed_date()
        if pd is None:
            return False
        ref = ref_date or datetime.now().date()
        return pd < ref

    def is_upcoming(self, ref_date: Optional[date] = None) -> bool:
        """Ritorna True se l'evento è oggi o in futuro rispetto a `ref_date`."""
        return not self.is_past(ref_date)

    @property
    def id(self) -> str:
        """ID univoco basato sull'URL normalizzato (senza source, per dedup cross-collector)."""
        normalized = _normalize_url(self.url)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @property
    def title_normalized(self) -> str:
        """Titolo normalizzato per confronto fuzzy."""
        return _normalize_title(self.title)

    def to_dict(self) -> dict[str, Any]:
        """Serializza l'evento in un dict, includendo le property calcolate."""
        data = {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "description": self.description,
            "date_str": self.date_str,
            "location": self.location,
            "organizer": self.organizer,
            "is_hackathon": self.is_hackathon,
            "confidence": self.confidence,
            "review_status": self.review_status,
            "review_reason": self.review_reason,
            "reviewed_at": self.reviewed_at,
            "alternate_urls": self.alternate_urls,
            "discovered_at": self.discovered_at,
        }
        return data

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, HackathonEvent):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)


class BaseCollector(ABC):
    """Interfaccia che ogni collector deve implementare."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Nome identificativo del collector (per logging e report)."""
        ...

    @abstractmethod
    def collect(self) -> list[HackathonEvent]:
        """Restituisce una lista di eventi grezzi (non ancora filtrati dal LLM).

        Ogni implementazione deve:
        - Gestire i propri errori di rete internamente
        - Ritornare una lista vuota (mai None) in caso di problemi
        - Loggare gli errori con logging standard
        """
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} ({self.name})>"
