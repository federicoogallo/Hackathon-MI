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
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
MEETUP_API_KEY = os.getenv("MEETUP_API_KEY", "")  # opzionale — migliora Meetup collector

# ─── Parametri ricerca ─────────────────────────────────────────────────────
SEARCH_LOCATION = "Milano"
SEARCH_COUNTRY = "Italy"
SEARCH_RADIUS_KM = 30

# ─── Keyword per i filtri ──────────────────────────────────────────────────
# Regex word-boundary (\b) per evitare falsi positivi (es. "jam" → "Jazz Jam")
POSITIVE_KEYWORDS = [
    # ── Core hackathon ──
    r"\bhackathon\b",
    r"\bhacka\w*\b",                    # hacka-thon, hacka-ton varianti
    r"\bhack\s*day\b",
    r"\bhack\s*fest\b",
    r"\bhack\s*week\b",
    r"\bhacker\w*\b",                   # HackerX, HackerSpace event, ...
    # ── *-athon varianti ──
    r"\bcodathon\b",
    r"\bcodeathon\b",
    r"\bbuildathon\b",
    r"\bappathon\b",
    r"\bmakeathon\b",
    r"\bmake[\-\s]?a[\-\s]?thon\b",
    r"\bideathon\b",
    r"\bdatathon\b",
    r"\bhealthathon\b",
    r"\bethathon\b",
    r"\bdesignathon\b",
    # ── Jam / Sprint / Marathon ──
    r"\bcode\s*jam\b",
    r"\bgame\s+jam\b",
    r"\bdev\s*jam\b",
    r"\bcode\s*sprint\b",
    r"\bdev\s*sprint\b",
    r"\bcoding\s+marathon\b",
    r"\bprogramming\s+marathon\b",
    # ── Challenge / Contest / Competition (EN) ──
    r"\bcoding\s+challenge\b",
    r"\bcoding\s+competition\b",
    r"\bcoding\s+contest\b",
    r"\bprogramming\s+challenge\b",
    r"\bprogramming\s+competition\b",
    r"\bprogramming\s+contest\b",
    r"\binnovation\s+challenge\b",
    r"\binnovation\s+competition\b",
    r"\btech\s+challenge\b",
    r"\btech\s+competition\b",
    r"\bai\s+challenge\b",
    r"\bai\s+competition\b",
    r"\bdata\s+challenge\b",
    r"\bdata\s+competition\b",
    r"\bstartup\s+competition\b",
    r"\bstartup\s+contest\b",
    r"\bpitch\s+competition\b",
    r"\bpitch\s+contest\b",
    r"\bopen\s+innovation\b",
    r"\bbuild\s+challenge\b",
    r"\bctf\b",                          # Capture The Flag
    r"\bcapture\s+the\s+flag\b",
    # ── Termini italiani ──
    r"\bcompetizione\s+(?:di\s+)?(?:coding|programmazione|tech|software|ai)\b",
    r"\bgara\s+(?:di\s+)?(?:coding|programmazione|informatica)\b",
    r"\bsfida\s+(?:tech|digitale|innovazione|coding)\b",
    r"\bconcorso\s+(?:tech|digitale|innovazione|programmazione)\b",
    r"\bmaratona\s+(?:di\s+)?(?:coding|programmazione|innovazione)\b",
    r"\bcompetizione\s+studentesc\w+\b",
    r"\bsfida\s+studentesc\w+\b",
    r"\bopen\s+call\b",                  # spesso usato per challenge/competition
    r"\bcall\s+for\s+(?:ideas?|innovation|solutions?|makers?)\b",
    # ── Bootcamp tech ──
    r"\bcoding\s+bootcamp\b",
    r"\btech\s+bootcamp\b",
    r"\bai\s+bootcamp\b",
    r"\bdev\s+bootcamp\b",
    # ── Format specifici ──
    r"\bcodefest\b",
    r"\bstartup\s+weekend\b",
    r"\bthon\b",                         # catchall per varianti non previste (buildthon, etc.)
]

NEGATIVE_KEYWORDS = [
    r"\blife\s*hack\w*\b",
    r"\bgrowth\s*hack\w*\b",
    r"\bikea\s*hack\w*\b",
    r"\bbiohack\w*\b",
    # Escludi competizioni sportive/culturali non tech
    r"\bconcorso\s+(?:musicale|canoro|fotografico|letterario|pittori|artistic\w+)\b",
    r"\bgara\s+(?:sportiva|ciclistica|automobilistica|calcio|nuoto|atletica)\b",
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
LLM_BATCH_SIZE = 5  # eventi per singola chiamata API (ridotto per rate-limit)
LLM_MAX_DESCRIPTION_LENGTH = 500  # troncamento descrizione
LLM_RETRY_MAX = 2
LLM_RETRY_DELAY = 10  # secondi base per exponential backoff

# ─── Dedup ──────────────────────────────────────────────────────────────────
FUZZY_DEDUP_THRESHOLD = 0.75  # SequenceMatcher ratio minimo per match

# ─── Parallelismo ──────────────────────────────────────────────────────────
MAX_COLLECTOR_WORKERS = 8
