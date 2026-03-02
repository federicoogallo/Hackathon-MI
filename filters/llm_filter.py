"""
Filtro LLM con Groq (Llama 3.3 70B) per classificare se un evento è un hackathon.

Usa batching per ridurre il numero di chiamate API.
Completamente gratuito: Groq offre 14.400 RPD e 30 RPM gratis (no carta richiesta).
Graceful degradation: se GROQ_API_KEY non è configurata, tutti gli eventi
passano (verrà usato solo il keyword filter).
"""

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime

from groq import Groq

import config
from models import HackathonEvent

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT_TEMPLATE = """Sei un classificatore RIGOROSO di eventi. Dati titolo, URL, location e descrizione, determina se è un HACKATHON REALE, FUTURO e FISICAMENTE A MILANO.

DATA ODIERNA: {current_date}

ATTENZIONE — Sii MOLTO SEVERO. È meglio scartare un evento dubbio che approvare un falso positivo.

CRITERI (TUTTI E 4 devono essere soddisfatti):

1. TIPO — L'evento deve essere una COMPETIZIONE/SFIDA A TEMPO LIMITATO dove si COSTRUISCE/PROGRAMMA qualcosa.
   SÌ: hackathon, code jam, game jam, coding challenge/contest, startup weekend, makeathon, datathon, CTF, innovation challenge CON building.
   NO: meetup, conferenze, workshop, corsi, webinar, career fair, demo day, networking, pitch senza coding, bootcamp formativi, pagine di listing/ricerca, profili utente.

2. CONTENUTO EVENTO — Il testo (titolo + descrizione) DEVE descrivere un EVENTO SPECIFICO con informazioni concrete (nome dell'hackathon, data, luogo, organizzatore).
   SÌ: pagine evento (lu.ma, eventbrite, devpost), siti ufficiali, ma ANCHE post social (LinkedIn, Facebook) che ANNUNCIANO un hackathon specifico con dettagli concreti.
   NO: pagine di ricerca/listing (eventbrite.it/d/...), homepage di organizzazioni, pagine di profilo, articoli generici senza riferimento a un evento specifico.
   NOTA: Un post LinkedIn/Facebook che annuncia un hackathon reale con data e luogo è VALIDO — conta il CONTENUTO, non il tipo di URL.

3. LOCATION — L'evento DEVE svolgersi FISICAMENTE a Milano o area metropolitana milanese.
   NO: eventi online/remoti/virtuali, eventi in altre città (Roma, Torino, Napoli...) o all'estero.
   ATTENZIONE: La location DEVE contenere esplicitamente "Milano", "Milan", "Politecnico", "Bocconi", "Bicocca", "MIND" o un indirizzo/luogo noto milanese.
   Se la location è vuota/non specificata e nulla nel titolo/descrizione/URL indica CHIARAMENTE Milano → is_hackathon: false.
   Il solo fatto che un'organizzazione (es. PoliHub) sia milanese NON basta: serve conferma esplicita nel testo.

4. TEMPO — L'evento DEVE essere futuro (data >= {current_date}) o senza data ma con indicazioni di essere nel {current_year} o futuro.
   NO: eventi passati, recap, articoli su eventi già avvenuti, edizioni precedenti. Se l'URL/titolo menziona solo anni < {current_year} → false.

ESTRAZIONE DATA — Se l'evento è approvato (is_hackathon: true), estrai la data di inizio nel campo "event_date" in formato YYYY-MM-DD.
- Cerca la data nel titolo, descrizione, URL (es. "10-11 April 2026" → "2026-04-10")
- Se ci sono più giorni (es. "26-27 febbraio 2026"), usa il PRIMO giorno
- Se trovi solo mese/anno ma non il giorno, usa il primo del mese (es. "maggio 2026" → "2026-05-01")
- Se non riesci a determinare la data → event_date: null
- Per eventi scartati (is_hackathon: false) → event_date: null

ESEMPI:
1. Titolo: "PoliHack 2026" | URL: lu.ma/polihack26 | Loc: "Politecnico Milano" → {{"is_hackathon": true, "confidence": 0.95, "reason": "Hackathon a Milano, futuro, pagina evento", "event_date": null}}
2. Titolo: "HSIL Hackathon 2026" | URL: linkedin.com/posts/... | Desc: "Global Hackathon on AI in Medicine, 10-11 April 2026 at MIND Milano" → {{"is_hackathon": true, "confidence": 0.90, "reason": "Post LinkedIn annuncia hackathon reale a Milano con data", "event_date": "2026-04-10"}}
3. Titolo: "Scopri hackathon su Eventbrite" | URL: eventbrite.it/d/italy--milano/hackathon → {{"is_hackathon": false, "confidence": 0.95, "reason": "Pagina di ricerca/listing, non evento specifico", "event_date": null}}
4. Titolo: "Hackathon recap 2024" | URL: blog.com/hackathon-2024 → {{"is_hackathon": false, "confidence": 0.90, "reason": "Evento passato (2024)", "event_date": null}}
5. Titolo: "Global Hackathon Online" | URL: hackathon.com/virtual → {{"is_hackathon": false, "confidence": 0.90, "reason": "Evento online, non a Milano", "event_date": null}}
6. Titolo: "Milan Game Jam 2026" | URL: globalgamejam.org/jam-sites/2026/milan | Loc: "SAE Institute Milano" | Desc: "30 Gennaio - 1 Febbraio 2026" → {{"is_hackathon": true, "confidence": 0.90, "reason": "Game jam fisico a Milano, futuro", "event_date": "2026-01-30"}}
7. Titolo: "Excited about my hackathon win!" | URL: linkedin.com/posts/... | Desc: "Great experience last weekend" → {{"is_hackathon": false, "confidence": 0.90, "reason": "Racconto personale, non annuncio evento futuro", "event_date": null}}
8. Titolo: "HSIL Hackathon 2026" | Desc: "10-11 April 2026 at MIND Milano" → {{"is_hackathon": true, "confidence": 0.95, "reason": "Hackathon a Milano, futuro", "event_date": "2026-04-10"}}

NEL DUBBIO → is_hackathon: false.

Rispondi SOLO con JSON: {{"results": [{{"index": 0, "is_hackathon": bool, "confidence": float, "reason": "stringa breve", "event_date": "YYYY-MM-DD o null"}}]}}"""


def _get_system_prompt() -> str:
    """Genera il system prompt con la data odierna (dinamico ad ogni chiamata)."""
    now = datetime.now()
    return _SYSTEM_PROMPT_TEMPLATE.format(
        current_date=now.strftime("%d %B %Y"),
        current_year=now.year,
    )


@dataclass
class LLMResult:
    """Risultato della classificazione LLM per un singolo evento."""
    is_hackathon: bool
    confidence: float
    reason: str
    event_date: str = ""  # Data estratta dal LLM in formato YYYY-MM-DD


def _build_user_prompt(events: list[HackathonEvent]) -> str:
    """Costruisce il prompt utente con la lista di eventi da classificare."""
    items = []
    for i, event in enumerate(events):
        desc = event.description[:config.LLM_MAX_DESCRIPTION_LENGTH]
        loc = event.location or "(non specificata)"
        items.append(
            f"{i}. Titolo: \"{event.title}\""
            f"\n   URL: {event.url}"
            f"\n   Location: \"{loc}\""
            f"\n   Descrizione: \"{desc}\""
        )
    return "Classifica questi eventi:\n\n" + "\n\n".join(items)


def _extract_json_objects(text: str) -> list[dict]:
    """Estrae oggetti JSON individuali da una stringa, anche se troncata.

    Usa un parser incrementale: scorre il testo cercando oggetti {...}
    completi. Questo gestisce i casi in cui il JSON array è troncato
    a metà dall'LLM (es. max_output_tokens raggiunto).
    """
    objects = []
    i = 0
    while i < len(text):
        if text[i] == '{':
            # Cerca la fine dell'oggetto contando le parentesi
            depth = 0
            start = i
            in_string = False
            escape_next = False
            for j in range(i, len(text)):
                ch = text[j]
                if escape_next:
                    escape_next = False
                    continue
                if ch == '\\' and in_string:
                    escape_next = True
                    continue
                if ch == '"' and not escape_next:
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        # Trovato oggetto completo
                        try:
                            obj = json.loads(text[start:j + 1])
                            if isinstance(obj, dict) and "is_hackathon" in obj:
                                objects.append(obj)
                        except json.JSONDecodeError:
                            pass
                        i = j + 1
                        break
            else:
                # Oggetto troncato — ignora
                break
        else:
            i += 1
    return objects


def _parse_llm_response(content: str, count: int) -> list[LLMResult]:
    """Parsa la risposta JSON del LLM.

    Args:
        content: Stringa JSON dal LLM.
        count: Numero di eventi attesi.

    Returns:
        Lista di LLMResult, uno per evento. Se il parsing fallisce,
        ritorna risultati "passanti" di default (meglio un falso positivo
        che perdere un hackathon vero).
    """
    default = [LLMResult(is_hackathon=False, confidence=0.0, reason="LLM parse error", event_date="") for _ in range(count)]

    # Step 1: Pulisci markdown code blocks
    cleaned = content.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)

    # Step 2: Prova parsing completo
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            # Cerca l'array nelle chiavi note, poi in qualsiasi valore (json_object mode)
            data = data.get("results", data.get("events", None))
            if data is None:
                raw = json.loads(cleaned)
                for v in raw.values():
                    if isinstance(v, list):
                        data = v
                        break
                else:
                    data = []
        if isinstance(data, list):
            results = []
            for item in data:
                results.append(LLMResult(
                    is_hackathon=bool(item.get("is_hackathon", True)),
                    confidence=float(item.get("confidence", 0.5)),
                    reason=str(item.get("reason", "")),
                    event_date=str(item.get("event_date") or ""),
                ))
            if len(results) != count:
                logger.warning(
                    "LLM ha ritornato %d risultati per %d eventi",
                    len(results), count,
                )
                while len(results) < count:
                    results.append(LLMResult(is_hackathon=False, confidence=0.0, reason="missing from LLM", event_date=""))
            return results[:count]
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        pass  # Prova il fallback

    # Step 3: Fallback — estrai oggetti JSON parziali (JSON troncato)
    logger.warning("JSON completo non parsabile, provo estrazione parziale — content: %s", content[:200])
    objects = _extract_json_objects(cleaned)

    if objects:
        logger.info("Estratti %d/%d risultati parziali dal JSON troncato", len(objects), count)
        # Mappa per indice
        by_index = {}
        for obj in objects:
            idx = obj.get("index")
            if idx is not None:
                by_index[int(idx)] = obj

        results = []
        for i in range(count):
            if i in by_index:
                item = by_index[i]
                results.append(LLMResult(
                    is_hackathon=bool(item.get("is_hackathon", True)),
                    confidence=float(item.get("confidence", 0.5)),
                    reason=str(item.get("reason", "")),
                    event_date=str(item.get("event_date") or ""),
                ))
            else:
                # Evento mancante — scarta per sicurezza
                results.append(LLMResult(is_hackathon=False, confidence=0.0, reason="missing from truncated LLM response", event_date=""))
        return results

    # Step 4: Nessun oggetto estratto — usa default
    logger.warning("Nessun risultato estraibile dalla risposta LLM")
    return default


def _get_groq_client():
    """Configura e restituisce il client Groq."""
    return Groq(api_key=config.GROQ_API_KEY)


def _call_llm(system_prompt: str, user_prompt: str) -> str:
    """Chiama Groq LLM con retry per rate limit.

    Returns:
        Il testo della risposta, o "[]" se tutti i tentativi falliscono.
    """
    for attempt in range(config.LLM_RETRY_MAX):
        try:
            client = _get_groq_client()
            response = client.chat.completions.create(
                model=config.LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=4096,
                response_format={"type": "json_object"},
            )
            return response.choices[0].message.content or "[]"

        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "rate_limit" in error_str.lower():
                delay = config.LLM_RETRY_DELAY * (2 ** attempt)
                logger.warning(
                    "Rate limit Groq (tentativo %d/%d) — attendo %ds",
                    attempt + 1, config.LLM_RETRY_MAX, delay,
                )
                time.sleep(delay)
                continue
            # Retry anche per errori di connessione / transient errors
            if any(kw in error_str.lower() for kw in ("connection", "timeout", "502", "503", "reset")):
                delay = config.LLM_RETRY_DELAY * (2 ** attempt)
                logger.warning(
                    "Errore connessione Groq (tentativo %d/%d) — attendo %ds: %s",
                    attempt + 1, config.LLM_RETRY_MAX, delay, error_str[:100],
                )
                time.sleep(delay)
                continue
            logger.error("Errore API Groq: %s", e)
            return ""

    logger.error("Rate limit Groq persistente dopo %d tentativi", config.LLM_RETRY_MAX)
    return ""


def classify_batch(events: list[HackathonEvent]) -> list[LLMResult]:
    """Classifica un batch di eventi usando Groq (Llama 3.3 70B).

    Args:
        events: Lista di eventi da classificare (max LLM_BATCH_SIZE).

    Returns:
        Lista di LLMResult, uno per evento.
    """
    if not config.GROQ_API_KEY:
        logger.warning("GROQ_API_KEY non configurata — skip filtro LLM (scarto tutto)")
        return [LLMResult(is_hackathon=False, confidence=0.0, reason="LLM disabled") for _ in events]

    user_prompt = _build_user_prompt(events)
    content = _call_llm(_get_system_prompt(), user_prompt)

    if not content:
        return [LLMResult(is_hackathon=False, confidence=0.0, reason="API error") for _ in events]

    return _parse_llm_response(content, len(events))


def llm_filter(events: list[HackathonEvent]) -> tuple[list[HackathonEvent], int]:
    """Classifica tutti gli eventi con il LLM, in batch.

    Aggiorna i campi `is_hackathon` e `confidence` di ogni evento.

    Returns:
        Tupla (eventi_confermati, conteggio_scartati).
    """
    if not events:
        return [], 0

    confirmed = []
    discarded = 0

    # Processa in batch
    for i in range(0, len(events), config.LLM_BATCH_SIZE):
        batch = events[i : i + config.LLM_BATCH_SIZE]

        # Pausa tra batch per rispettare rate limit (30 RPM free)
        if i > 0:
            time.sleep(8)

        results = classify_batch(batch)

        for event, result in zip(batch, results):
            event.is_hackathon = result.is_hackathon
            event.confidence = result.confidence

            # Popola date_str dal LLM se l'evento non ne ha già una
            if result.event_date and result.event_date.lower() not in ("null", "none", ""):
                if not event.date_str.strip():
                    event.date_str = result.event_date
                    logger.info(
                        "LLM DATA ESTRATTA: '%s' → %s",
                        event.title[:50], result.event_date,
                    )

            if result.is_hackathon and result.confidence >= config.LLM_CONFIDENCE_THRESHOLD:
                confirmed.append(event)
                logger.info(
                    "LLM CONFERMATO: '%s' (conf=%.2f, date=%s, reason=%s)",
                    event.title, result.confidence, event.date_str or "TBD", result.reason,
                )
            else:
                discarded += 1
                logger.info(
                    "LLM SCARTATO: '%s' (hackathon=%s, conf=%.2f, reason=%s)",
                    event.title, result.is_hackathon, result.confidence, result.reason,
                )

    return confirmed, discarded


# ─── Dedup semantica con LLM ────────────────────────────────────────────────

DEDUP_SYSTEM_PROMPT = """Sei un deduplicatore di eventi. Ti viene data una lista di hackathon confermati.
Alcuni potrebbero riferirsi allo STESSO EVENTO anche se hanno titoli o URL leggermente diversi
(es. pagine in lingue diverse, fonti diverse, o varianti del nome).

Raggruppali: restituisci un array JSON dove ogni elemento rappresenta UN evento unico.
Ogni elemento ha:
- "group": lista di indici (0-based) degli eventi che sono lo stesso evento
- "best_title": il titolo migliore/piu' completo da usare
- "best_url": l'URL piu' utile (preferisci eventbrite, lu.ma, siti ufficiali)

Se un evento e' unico, il group conterra' solo il suo indice.
Rispondi SOLO con l'array JSON."""


def llm_dedup(events: list[HackathonEvent]) -> list[HackathonEvent]:
    """Usa il LLM per raggruppare eventi duplicati semanticamente.

    Returns:
        Lista di eventi unici (il migliore per ogni gruppo).
    """
    if len(events) <= 1:
        return events

    if not config.GROQ_API_KEY:
        logger.warning("GROQ_API_KEY mancante — skip LLM dedup")
        return events

    # Costruisci prompt
    items = []
    for i, ev in enumerate(events):
        items.append(f"{i}. Titolo: \"{ev.title}\"\n   URL: {ev.url}\n   Fonte: {ev.source}")
    user_prompt = "Raggruppa questi hackathon (rimuovi duplicati):\n\n" + "\n\n".join(items)

    content = _call_llm(DEDUP_SYSTEM_PROMPT, user_prompt)
    if not content:
        logger.warning("LLM dedup: risposta vuota, nessuna dedup")
        return events

    # Parse risposta
    cleaned = content.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)

    try:
        groups = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("LLM dedup: JSON non valido, nessuna dedup")
        return events

    if isinstance(groups, dict):
        groups = groups.get("groups", groups.get("results", []))
    if not isinstance(groups, list) or not groups:
        logger.warning("LLM dedup: risposta non parsabile, nessuna dedup")
        return events

    # Costruisci lista unica
    unique_events: list[HackathonEvent] = []
    used_indices: set[int] = set()

    for group in groups:
        indices = group.get("group", [])
        if not indices:
            continue

        # Filtra indici gia' usati o fuori range
        valid_indices = [i for i in indices if i < len(events) and i not in used_indices]
        if not valid_indices:
            continue

        for i in valid_indices:
            used_indices.add(i)

        # Prendi l'evento "migliore" del gruppo
        best_idx = valid_indices[0]
        best_event = events[best_idx]

        # Usa il best_title e best_url dal LLM se forniti
        best_title = group.get("best_title", best_event.title)
        best_url = group.get("best_url", best_event.url)

        # Trova l'evento col best_url se esiste nel gruppo
        for i in valid_indices:
            if events[i].url == best_url:
                best_event = events[i]
                break

        # Aggiorna titolo se il LLM ne ha scelto uno migliore
        best_event.title = best_title

        # Raccogli URL alternativi
        for i in valid_indices:
            if events[i].url != best_event.url:
                best_event.alternate_urls.append(events[i].url)

        if len(valid_indices) > 1:
            logger.info(
                "LLM DEDUP: raggruppati %d eventi -> '%s'",
                len(valid_indices), best_event.title,
            )

        unique_events.append(best_event)

    # Aggiungi eventuali eventi non inclusi in nessun gruppo
    for i, ev in enumerate(events):
        if i not in used_indices:
            unique_events.append(ev)
            logger.warning("LLM DEDUP: evento %d non in nessun gruppo, incluso: '%s'", i, ev.title)

    logger.info("LLM DEDUP: %d eventi -> %d unici", len(events), len(unique_events))
    return unique_events
