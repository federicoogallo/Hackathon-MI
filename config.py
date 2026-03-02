"""
Configurazione centralizzata.

Tutte le API key e parametri sono letti da variabili d'ambiente.
In locale, usa un file .env (caricato tramite python-dotenv).
Su GitHub Actions, usa i Secrets del repository.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Carica .env solo se esiste (in locale)
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

# ─── Percorsi ───────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
EVENTS_FILE = DATA_DIR / "events.json"

# ─── API Keys ──────────────────────────────────────────────────────────────
EVENTBRITE_API_KEY = os.getenv("EVENTBRITE_API_KEY", "")
GOOGLE_CSE_API_KEY = os.getenv("GOOGLE_CSE_API_KEY", "")
GOOGLE_CSE_CX = os.getenv("GOOGLE_CSE_CX", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ─── Parametri ricerca ─────────────────────────────────────────────────────
SEARCH_LOCATION = "Milano"
SEARCH_COUNTRY = "Italy"
SEARCH_RADIUS_KM = 30

# ─── Keyword per i filtri ──────────────────────────────────────────────────
# Regex word-boundary (\b) per evitare falsi positivi (es. "jam" → "Jazz Jam")
POSITIVE_KEYWORDS = [
    # ── Core ──
    r"\bhackathon\b",
    r"\bhacka\w*\b",            # hacka-thon, hacka-ton varianti
    r"\bhack\s*day\b",
    r"\bhack\s*fest\b",
    r"\bhack\s*week\b",
    # ── *-athon varianti ──
    r"\bcodathon\b",
    r"\bcodeathon\b",
    r"\bbuildathon\b",
    r"\bappathon\b",
    r"\bmakeathon\b",
    r"\bmake[\-\s]?a[\-\s]?thon\b",  # make-a-thon, make a thon
    r"\bideathon\b",
    r"\bdatathon\b",
    r"\bhealthathon\b",
    r"\bethathon\b",
    r"\bdesignathon\b",
    # ── Jam / Sprint ──
    r"\bcode\s*jam\b",
    r"\bgame\s+jam\b",
    r"\bdev\s*jam\b",
    r"\bcode\s*sprint\b",
    r"\bdev\s*sprint\b",
    # ── Challenge / Contest / Competition ──
    r"\bcoding\s+challenge\b",
    r"\bcoding\s+competition\b",
    r"\bcoding\s+contest\b",
    r"\bcoding\s+marathon\b",
    r"\binnovation\s+challenge\b",
    r"\btech\s+challenge\b",
    # ── Format specifici ──
    r"\bcodefest\b",
    r"\bstartup\s+weekend\b",
]

NEGATIVE_KEYWORDS = [
    r"\blife\s*hack\w*\b",
    r"\bgrowth\s*hack\w*\b",
    r"\bikea\s*hack\w*\b",
    r"\bbiohack\w*\b",
]

# ─── HTTP ───────────────────────────────────────────────────────────────────
HTTP_TIMEOUT = 30  # secondi
HTTP_MAX_RETRIES = 3
HTTP_BACKOFF_FACTOR = 1.5
HTTP_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# ─── LLM (Groq — Llama 3.3 70B) ─────────────────────────────────────────────
# Groq free tier: 14.400 RPD, 30 RPM (vs Gemini 20 RPD)
LLM_MODEL = "llama-3.3-70b-versatile"
LLM_CONFIDENCE_THRESHOLD = 0.7
LLM_BATCH_SIZE = 20  # eventi per singola chiamata API
LLM_MAX_DESCRIPTION_LENGTH = 500  # troncamento descrizione
LLM_RETRY_MAX = 3
LLM_RETRY_DELAY = 5  # secondi base per exponential backoff (Groq è veloce)

# ─── Dedup ──────────────────────────────────────────────────────────────────
FUZZY_DEDUP_THRESHOLD = 0.85  # SequenceMatcher ratio minimo per match

# ─── Parallelismo ──────────────────────────────────────────────────────────
MAX_COLLECTOR_WORKERS = 5
