"""
Bot Telegram per Hackathon Monitor.

Comandi: /scan (avvia scansione), /help. Accetta solo il CHAT_ID configurato.
I dettagli degli hackathon sono consultabili sul sito GitHub Pages.
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
    "/help — Questo messaggio\n"
    "\n"
    '🌐 <a href="https://federicoogallo.github.io/Hackathon-MI/">Vedi tutti gli hackathon</a>'
)


def _handle_start(chat_id: int) -> None:
    _send(chat_id, _HELP_TEXT)


def _handle_help(chat_id: int) -> None:
    _send(chat_id, _HELP_TEXT)








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
    "/scan": _handle_scan,
}
