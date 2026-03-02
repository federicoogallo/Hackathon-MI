"""
Bot Telegram per Hackathon Monitor.

Comandi: /scan (avvia scansione), /report (dettaglio ultima run),
/status (storico eventi), /help. Accetta solo il CHAT_ID configurato.
"""

import atexit
import os

# Disabilita proxy per Telegram (evita 403 da proxy aziendale/VPN)
for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(k, None)

import json
import logging
import time
import threading
from pathlib import Path
from datetime import datetime

import requests

import config

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}"

# Session che ignora proxy di sistema (trust_env=False) + nessun proxy esplicito
_session = requests.Session()
_session.trust_env = False
_session.proxies = {"http": None, "https": None}


def _api_url(method: str) -> str:
    return f"{TELEGRAM_API.format(token=config.TELEGRAM_BOT_TOKEN)}/{method}"


def _send(chat_id: str | int, text: str) -> bool:
    """Invia un messaggio Telegram."""
    try:
        resp = _session.post(
            _api_url("sendMessage"),
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
        return resp.status_code == 200
    except Exception as e:
        logger.error("Errore invio messaggio: %s", e)
        return False


def _is_authorized(chat_id: int) -> bool:
    """Verifica che il messaggio provenga dal chat_id autorizzato."""
    return str(chat_id) == str(config.TELEGRAM_CHAT_ID)


def _escape_html(s: str) -> str:
    """Escape per HTML Telegram."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ─── Handlers dei comandi ───────────────────────────────────────────────────


_HELP_TEXT = (
    "🏆 <b>Hackathon Monitor · Milano</b>\n"
    "<i>Scansiono hackathon a Milano e ti notifico i nuovi.</i>\n"
    "\n"
    "<b>Comandi</b>\n"
    "/scan — Avvia una scansione ora\n"
    "/eventi — Hackathon futuri confermati\n"
    "/report — Dettaglio ultima scansione\n"
    "/status — Statistiche storico\n"
    "/fonti — Sorgenti monitorate\n"
    "/help — Questo messaggio"
)


def _handle_start(chat_id: int) -> None:
    _send(chat_id, _HELP_TEXT)


def _handle_help(chat_id: int) -> None:
    _send(chat_id, _HELP_TEXT)


def _handle_report(chat_id: int) -> None:
    report_path = Path(config.DATA_DIR) / "last_report.json"
    if not report_path.exists():
        _send(chat_id, (
            "📊 <b>Ultima scansione</b>\n"
            "<i>Nessun report disponibile.</i>\n\n"
            "Esegui /scan per avviare la prima scansione."
        ))
        return

    try:
        report = json.loads(report_path.read_text())
    except (json.JSONDecodeError, OSError):
        _send(chat_id, "⚠️ Impossibile leggere il report.")
        return

    failed = report.get("failed_collectors", [])
    date = _escape_html(str(report.get("date", "—")))
    collectors_ok = int(report.get("collectors_ok", 0))
    collectors_total = int(report.get("collectors_total", 0))
    raw = int(report.get("raw_events", 0))
    post_dedup = int(report.get("post_dedup", 0))
    post_kw = int(report.get("post_keyword", 0))
    post_llm = int(report.get("post_llm", 0))
    new_ev = int(report.get("new_events", 0))
    total_stored = int(report.get("total_stored", 0))

    collector_status = (
        f"⚠️ Falliti: {_escape_html(', '.join(failed))}"
        if failed
        else "✅ Tutti i collector ok"
    )

    lines = [
        "📊 <b>Ultima scansione</b>",
        f"<i>{date}</i>",
        "",
        f"🌐 Collector: <b>{collectors_ok}/{collectors_total}</b>  {collector_status}",
        "",
        "<b>Pipeline</b>",
        f"  Raw raccolti:   <code>{raw}</code>",
        f"  Post dedup:     <code>{post_dedup}</code>",
        f"  Post keyword:   <code>{post_kw}</code>",
        f"  Post LLM:       <code>{post_llm}</code>",
        "",
        f"🆕 Nuovi notificati: <b>{new_ev}</b>",
        f"📚 Storico totale:   <b>{total_stored}</b> eventi",
    ]

    _send(chat_id, "\n".join(lines))


def _handle_status(chat_id: int) -> None:
    events_path = Path(config.EVENTS_FILE)
    if not events_path.exists():
        _send(chat_id, (
            "📚 <b>Storico eventi</b>\n"
            "<i>Nessun evento ancora salvato.</i>\n\n"
            "Esegui /scan per avviare la prima scansione."
        ))
        return

    try:
        data = json.loads(events_path.read_text())
        events = data.get("events", [])
        if isinstance(events, dict):
            events = list(events.values())
        total = len(events)
        confirmed = sum(1 for e in events if e.get("is_hackathon"))
        upcoming = sum(
            1 for e in events
            if e.get("is_hackathon") and _event_is_upcoming(e)
        )
        last_check = _escape_html(str(data.get("last_check") or "—"))
        _send(chat_id, (
            "📚 <b>Storico eventi</b>\n"
            f"<i>Aggiornato: {last_check}</i>\n\n"
            f"📦 Totale in archivio:    <b>{total}</b>\n"
            f"✅ Hackathon confermati: <b>{confirmed}</b>\n"
            f"📅 In arrivo (futuri):   <b>{upcoming}</b>\n\n"
            "<i>Usa /eventi per vedere gli hackathon futuri.</i>"
        ))
    except (json.JSONDecodeError, OSError):
        _send(chat_id, "⚠️ Impossibile leggere lo storico.")


def _event_is_upcoming(e: dict) -> bool:
    """Verifica se un evento dict è futuro o senza data."""
    from models import HackathonEvent
    try:
        ev = HackathonEvent(
            title=e.get("title", ""),
            url=e.get("url", ""),
            source=e.get("source", ""),
            date_str=e.get("date_str", ""),
        )
        return ev.is_upcoming()
    except Exception:
        return True  # In caso di errore, includi l'evento


def _event_sort_key(e: dict):
    """Chiave di ordinamento per data: eventi con data in ordine crescente, senza data alla fine."""
    from models import HackathonEvent
    from datetime import date
    try:
        ev = HackathonEvent(
            title=e.get("title", ""),
            url=e.get("url", ""),
            source=e.get("source", ""),
            date_str=e.get("date_str", ""),
        )
        d = ev.parsed_date()
        return d if d is not None else date(9999, 12, 31)
    except Exception:
        from datetime import date
        return date(9999, 12, 31)


def _format_date_compact(date_str: str) -> str:
    """Formatta una data in formato compatto (es. '15 mar 2026'). Ritorna stringa vuota se non parsabile."""
    from models import HackathonEvent
    if not (date_str or "").strip():
        return ""
    try:
        ev = HackathonEvent(title="", url="", source="", date_str=date_str)
        d = ev.parsed_date()
        if d:
            months = ["gen", "feb", "mar", "apr", "mag", "giu",
                      "lug", "ago", "set", "ott", "nov", "dic"]
            return f"{d.day} {months[d.month - 1]} {d.year}"
    except Exception:
        pass
    return date_str.strip()[:20]


def _handle_eventi(chat_id: int) -> None:
    """Hackathon futuri confermati dall'LLM, ordinati per data."""
    events_path = Path(config.EVENTS_FILE)
    if not events_path.exists():
        _send(chat_id, (
            "📅 <b>Hackathon in arrivo</b>\n"
            "<i>Nessun evento nello storico.</i>\n\n"
            "Esegui /scan per avviare la prima scansione."
        ))
        return
    try:
        data = json.loads(events_path.read_text())
        all_events = data.get("events", [])
        if isinstance(all_events, dict):
            all_events = list(all_events.values())
    except (json.JSONDecodeError, OSError):
        _send(chat_id, "⚠️ Impossibile leggere lo storico.")
        return

    # Filtra: solo hackathon confermati dall'LLM e con data futura (o senza data)
    upcoming = [
        e for e in all_events
        if e.get("is_hackathon") and _event_is_upcoming(e)
    ]

    if not upcoming:
        _send(chat_id, (
            "📅 <b>Hackathon in arrivo</b>\n"
            "<i>Nessun hackathon futuro confermato al momento.</i>\n\n"
            "Esegui /scan per aggiornare la lista."
        ))
        return

    # Ordina per data crescente (prima i più vicini)
    upcoming.sort(key=_event_sort_key)
    shown = upcoming[:10]

    lines = [
        "📅 <b>Hackathon in arrivo</b>",
        f"<i>{len(upcoming)} eventi confermati · ordinati per data</i>",
        "",
    ]
    for i, e in enumerate(shown, 1):
        title = (e.get("title") or "Senza titolo").strip()
        if len(title) > 52:
            title = title[:49] + "…"
        url = e.get("url", "")
        date_str = e.get("date_str", "")
        location = (e.get("location") or "").strip()

        date_compact = _format_date_compact(date_str)
        meta_parts = []
        if date_compact:
            meta_parts.append(f"📅 {_escape_html(date_compact)}")
        if location and location.lower() not in ("milano", "milan", ""):
            meta_parts.append(f"📍 {_escape_html(location[:30])}")
        elif location:
            meta_parts.append("📍 Milano")

        title_line = f"{i}. <a href=\"{url}\">{_escape_html(title)}</a>"
        lines.append(title_line)
        if meta_parts:
            lines.append("    " + "  ·  ".join(meta_parts))

    if len(upcoming) > 10:
        lines.append(f"\n<i>... e altri {len(upcoming) - 10} eventi. Esegui /scan per aggiornare.</i>")
    else:
        lines.append("\n<i>Esegui /scan per aggiornare la lista.</i>")

    _send(chat_id, "\n".join(lines))


def _handle_fonti(chat_id: int) -> None:
    """Elenco delle fonti monitorate."""
    _send(chat_id, (
        "🔍 <b>Sorgenti monitorate</b>\n"
        "<i>Aggiornate ad ogni scansione</i>\n\n"
        "<b>Piattaforme eventi</b>\n"
        "  · Eventbrite\n"
        "  · Devpost\n"
        "  · Luma\n"
        "  · InnovUp\n\n"
        "<b>Istituzioni</b>\n"
        "  · PoliHub\n"
        "  · PoliMi, Bocconi, Bicocca\n\n"
        "<b>Web &amp; community</b>\n"
        "  · Ricerca web (DuckDuckGo)\n"
        "  · Reddit (r/ItalyInformatica, r/italy)\n\n"
        "🤖 <b>Filtro AI</b>\n"
        "  Keyword filter + LLM (Groq · Llama 3.3 70B)\n"
        "  <i>Conferma che l'evento sia un vero hackathon a Milano</i>"
    ))


def _handle_reset_history(chat_id: int) -> None:
    """Comando one-shot per cancellare lo storico e i report.

    Questo comando può essere eseguito una sola volta: crea un file marker
    `data/.history_cleared` per impedire esecuzioni successive.
    """
    marker = Path(config.DATA_DIR) / ".history_cleared"
    if marker.exists():
        _send(chat_id, (
            "ℹ️ <b>Operazione non disponibile</b>\n"
            "<i>Lo storico è già stato cancellato in precedenza.\n"
            "L'operazione può essere eseguita una sola volta.</i>"
        ))
        return

    # Elimina file noti (se presenti)
    removed = []
    targets = [
        Path(config.EVENTS_FILE),
        Path(config.DATA_DIR) / "last_report.json",
        Path(config.DATA_DIR) / "pending_notifications.json",
    ]
    for p in targets:
        try:
            if p.exists():
                p.unlink()
                removed.append(str(p))
        except Exception as e:
            logger.warning("Impossibile rimuovere %s: %s", p, e)

    # Crea marker per non ripetere l'operazione
    try:
        Path(config.DATA_DIR).mkdir(parents=True, exist_ok=True)
        marker.write_text(datetime.now().isoformat())
    except Exception as e:
        logger.error("Impossibile creare marker storico cancellato: %s", e)
        _send(chat_id, (
            "⚠️ <b>Errore durante il reset</b>\n"
            "<i>Impossibile creare il marker. Controlla i permessi sul filesystem.</i>"
        ))
        return

    msg_lines = [
        "🗑️ <b>Storico cancellato</b>",
        "",
        f"<i>Rimossi {len(removed)} file.</i>",
    ]
    if removed:
        msg_lines.append("\n".join([_escape_html(r) for r in removed]))

    msg_lines.append("\n<i>Operazione eseguita una sola volta — non può essere ripetuta.</i>")
    _send(chat_id, "\n".join(msg_lines))


_scan_lock = threading.Lock()
_scan_in_progress = False


def _handle_scan(chat_id: int) -> None:
    """Avvia una scansione (non bloccante)."""
    global _scan_in_progress

    if not _is_authorized(chat_id):
        logger.warning("Tentativo di /scan da chat non autorizzata: %s", chat_id)
        _send(chat_id, "⛔ <b>Accesso non autorizzato.</b>")
        return

    # Evita scansioni concorrenti
    if _scan_in_progress:
        _send(chat_id, (
            "⏳ <b>Scansione già in corso</b>\n"
            "<i>Attendi il completamento prima di rilanciare.</i>"
        ))
        return

    def _run_scan():
        global _scan_in_progress
        _scan_in_progress = True
        try:
            _send(chat_id, (
                "🔎 <b>Scansione avviata</b>\n"
                "<i>Sto cercando hackathon su tutte le sorgenti...\n"
                "Ti avviso al termine.</i>"
            ))
            import main as _main

            _main.run_pipeline(dry_run=False)
            _send(chat_id, (
                "✅ <b>Scansione completata</b>\n"
                "<i>Usa /report per il riepilogo o /eventi per gli hackathon in arrivo.</i>"
            ))
        except Exception as e:
            logger.exception("Errore durante la scansione richiesta da bot: %s", e)
            _send(chat_id, (
                "⚠️ <b>Errore durante la scansione</b>\n"
                "<i>Controlla i log per i dettagli.</i>"
            ))
        finally:
            _scan_in_progress = False

    threading.Thread(target=_run_scan, daemon=True).start()


# ─── Long Polling ───────────────────────────────────────────────────────────


def _ensure_single_instance() -> bool:
    """Garantisce una sola istanza del bot. Ritorna False se un'altra è già in esecuzione."""
    lock_path = Path(config.DATA_DIR) / ".bot.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if lock_path.exists():
            old_pid = int(lock_path.read_text().strip())
            try:
                os.kill(old_pid, 0)  # Verifica se il processo esiste
                logger.error("Un'altra istanza del bot è già in esecuzione (PID %d). Termina quella prima.", old_pid)
                return False
            except OSError:
                pass  # Processo non esiste, lock obsoleto
        lock_path.write_text(str(os.getpid()))
        def _remove_lock():
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass
        atexit.register(_remove_lock)
        return True
    except Exception as e:
        logger.warning("Impossibile creare lock singola istanza: %s", e)
        return True  # Procedi comunque


def start_polling():
    """Avvia il bot in modalità long polling."""
    # Verifica presenza token
    if not config.TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN non configurato — impossibile avviare il bot")
        return

    if not _ensure_single_instance():
        return

    logger.info("Bot Telegram avviato — in ascolto comandi...")
    # Verifica connettività all'avvio
    try:
        r = _session.get(_api_url("getMe"), timeout=10)
        if r.status_code == 200:
            logger.info("Connessione a Telegram OK")
        else:
            logger.warning("getMe risposta %d: %s", r.status_code, r.text[:200])
    except requests.exceptions.RequestException as e:
        logger.error(
            "Impossibile raggiungere api.telegram.org — verifica internet/firewall/proxy: %s",
            e,
        )

    offset = 0

    while True:
        try:
            resp = _session.get(
                _api_url("getUpdates"),
                params={"offset": offset, "timeout": 30},
                timeout=35,
            )
            if resp.status_code != 200:
                logger.error("getUpdates errore %d", resp.status_code)
                time.sleep(5)
                continue

            data = resp.json()
            for update in data.get("result", []):
                offset = update["update_id"] + 1
                _process_update(update)

        except requests.exceptions.Timeout:
            continue
        except requests.exceptions.ConnectionError as e:
            logger.warning("Connessione persa — riprovo tra 5s: %s", e)
            time.sleep(5)
        except Exception as e:
            logger.error("Errore polling: %s", e)
            time.sleep(5)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    start_polling()


# ─── Message processing / dispatcher ──────────────────────────────────────


def _process_update(update: dict) -> None:
    """Elabora un update ricevuto da Telegram e instrada al relativo handler."""
    message = update.get("message") or update.get("edited_message")
    if not message:
        return

    chat = message.get("chat", {})
    chat_id = chat.get("id")
    text = (message.get("text") or "").strip()

    if not chat_id:
        return

    # Messaggio senza testo (foto, sticker, ecc.)
    if not text:
        if not _is_authorized(chat_id):
            return
        _send(chat_id, "<i>Scrivi un comando, ad esempio /help</i>")
        return

    # Controllo autorizzazione
    if not _is_authorized(chat_id):
        logger.warning("Messaggio ignorato da chat_id non autorizzato: %s", chat_id)
        _send(chat_id, "⛔ Accesso non autorizzato.")
        return

    # Estrai il comando (prima parola; gestisci /command@botname)
    first_word = text.split()[0] if text.split() else ""
    command = first_word.split("@")[0].lower()

    handler = COMMANDS.get(command)
    if handler:
        logger.info("Comando ricevuto: %s", command)
        try:
            handler(chat_id)
        except Exception:
            logger.exception("Errore eseguendo handler per %s", command)
            _send(chat_id, "⚠️ <b>Errore interno</b>\n<i>Riprova o controlla i log.</i>")
    else:
        logger.info("Messaggio non comando, invio help: %r", text[:50])
        _send(chat_id, "❓ <b>Comando non riconosciuto.</b>\n<i>Scrivi /help per l'elenco comandi.</i>")


# Mappa comandi -> handler
COMMANDS = {
    "/start": _handle_start,
    "/help": _handle_help,
    "/report": _handle_report,
    "/eventi": _handle_eventi,
    "/status": _handle_status,
    "/fonti": _handle_fonti,
    "/reset_history": _handle_reset_history,
    "/scan": _handle_scan,
}
