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


_SYSTEM_PROMPT_TEMPLATE = """Sei un classificatore di eventi. Dati il titolo e la descrizione di un evento, determina se è un HACKATHON (o evento assimilabile) FUTURO accessibile da MILANO.

DATA ODIERNA: {current_date}

CRITERI (TUTTI e 3 devono essere soddisfatti):
1. TIPO: L'evento deve essere una competizione/sfida a tempo limitato dove si costruisce/programma qualcosa. Include: hackathon, hack day/week/fest, appathon/codathon/buildathon/makeathon/datathon e simili, code jam, game jam, coding challenge/competition/contest, programming competition/contest, startup weekend, codefest, innovation challenge (con componente di building/coding), CTF (Capture The Flag), open innovation con prototipazione. NON include: meetup, conferenze, workshop, corsi, webinar, career fair, demo day, aperitivi tech, networking puro, pitch competition SENZA coding, bootcamp PURAMENTE formativi (senza gara/premi).
2. LOCATION: L'evento DEVE svolgersi FISICAMENTE a Milano o nell'area metropolitana milanese/Lombardia. Eventi online, remoti o virtuali → is_hackathon: false. Se l'evento è in un'altra città italiana (Roma, Torino, Napoli, Bari, ecc.) o all'estero → is_hackathon: false.
3. TEMPO: L'evento DEVE essere futuro o in corso (data >= oggi). Se l'evento è chiaramente nel passato (es. "Hackathon 2024", date già trascorse) → is_hackathon: false. Se la data non è specificata ma non ci sono indicazioni che sia passato → lascia passare. Se un evento è ricorrente (es. "Global Game Jam"), consideralo solo se l'edizione è del {current_year} o futura.

ESEMPI:
1. "PoliHack 2026 — 24h coding marathon" (Milano) → {{"is_hackathon": true, "confidence": 0.95, "reason": "Hackathon competitivo 24h a Milano, futuro"}}
2. "AI Coding Challenge Milano 2026" → {{"is_hackathon": true, "confidence": 0.90, "reason": "Competizione coding con tema AI a Milano"}}
3. "CASSINI Hackathon - Space for Water" (Online, remoto) → {{"is_hackathon": false, "confidence": 0.90, "reason": "Evento online/remoto, non fisicamente a Milano"}}
4. "Hackathon Milano 2024 — recap" → {{"is_hackathon": false, "confidence": 0.95, "reason": "Evento passato (2024)"}}
5. "Hackathon Taranto 2026" (solo in presenza Taranto) → {{"is_hackathon": false, "confidence": 0.90, "reason": "Hackathon fisico non a Milano"}}
6. "Corso full-stack bootcamp Milano" → {{"is_hackathon": false, "confidence": 0.90, "reason": "Bootcamp formativo, non gara"}}
7. "HackerX Milan — Job Fair 2026" → {{"is_hackathon": false, "confidence": 0.88, "reason": "Evento recruiting, non competizione"}}

Rispondi SOLO con un oggetto JSON con chiave "results" contenente un array. Per ogni evento nell'input, restituisci un oggetto con:
- "index": indice dell'evento (partendo da 0)
- "is_hackathon": bool
- "confidence": float 0-1
- "reason": stringa breve (max 50 parole)

Formato: {{"results": [{{"index": 0, "is_hackathon": true, "confidence": 0.95, "reason": "..."}}]}}"""


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


def _build_user_prompt(events: list[HackathonEvent]) -> str:
    """Costruisce il prompt utente con la lista di eventi da classificare."""
    items = []
    for i, event in enumerate(events):
        desc = event.description[:config.LLM_MAX_DESCRIPTION_LENGTH]
        items.append(f"{i}. Titolo: \"{event.title}\"\n   Descrizione: \"{desc}\"")
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
    default = [LLMResult(is_hackathon=True, confidence=0.5, reason="LLM parse error") for _ in range(count)]

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
                ))
            if len(results) != count:
                logger.warning(
                    "LLM ha ritornato %d risultati per %d eventi",
                    len(results), count,
                )
                while len(results) < count:
                    results.append(LLMResult(is_hackathon=True, confidence=0.5, reason="missing from LLM"))
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
                ))
            else:
                # Evento mancante — lascia passare per sicurezza
                results.append(LLMResult(is_hackathon=True, confidence=0.5, reason="missing from truncated LLM response"))
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
        logger.warning("GROQ_API_KEY non configurata — skip filtro LLM")
        return [LLMResult(is_hackathon=True, confidence=0.5, reason="LLM disabled") for _ in events]

    user_prompt = _build_user_prompt(events)
    content = _call_llm(_get_system_prompt(), user_prompt)

    if not content:
        return [LLMResult(is_hackathon=True, confidence=0.5, reason="API error") for _ in events]

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

        # Pausa tra batch per rispettare rate limit (15 RPM free)
        if i > 0:
            time.sleep(5)

        results = classify_batch(batch)

        for event, result in zip(batch, results):
            event.is_hackathon = result.is_hackathon
            event.confidence = result.confidence

            if result.is_hackathon and result.confidence >= config.LLM_CONFIDENCE_THRESHOLD:
                confirmed.append(event)
                logger.info(
                    "LLM CONFERMATO: '%s' (conf=%.2f, reason=%s)",
                    event.title, result.confidence, result.reason,
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
