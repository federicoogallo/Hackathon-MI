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
    r"\bhack\s*night\b",
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
    r"\bcreathon\b",
    r"\binnovathon\b",
    r"\bclimathon\b",
    # ── *-thon catchall (escluse maratona/telethon/walkathon/python) ──
    r"\b(?!mara|tele|walk|py)\w+a?thon\b",
    # ── Jam / Sprint / Marathon ──
    r"\bcode\s*jam\b",
    r"\bgame\s+jam\b",
    r"\bdev\s*jam\b",
    r"\bcode\s*sprint\b",
    r"\bdev\s*sprint\b",
    r"\binnovation\s+sprint\b",
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
    r"\btech\s+contest\b",
    r"\bai\s+challenge\b",
    r"\bai\s+competition\b",
    r"\bdata\s+challenge\b",
    r"\bdata\s+competition\b",
    r"\bdigital\s+challenge\b",
    r"\bdigital\s+competition\b",
    r"\bstartup\s+competition\b",
    r"\bstartup\s+contest\b",
    r"\bpitch\s+competition\b",
    r"\bpitch\s+contest\b",
    r"\bopen\s+innovation\b",
    r"\bbuild\s+challenge\b",
    r"\bsmart\s+city\s+challenge\b",
    r"\bsocial\s+innovation\s+(?:challenge|competition)\b",
    # ── CTF (con contesto per evitare writeup/blog) ──
    r"\bctf\s+(?:competition|event|challenge|20\d{2})\b",
    r"\bcapture\s+the\s+flag\b",
    # ── Hack + contesto specifico ──
    r"\bhack\s+for\s+\w+\b",             # "Hack for Good", "Hack for Climate"
    r"\b\w+\s+hack\s+20\d{2}\b",        # "Climate Hack 2026"
    r"\b\w+hack\s+20\d{2}\b",           # "PoliHack 2026" (parola composta)
    r"\burban\s+hack\w*\b",
    r"\bcivic\s+hack\w*\b",
    r"\bweb3?\s*(?:hackathon|hack)\b",
    r"\bdefi\s+hack\w*\b",
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
    r"\bhacknight\b",
]

NEGATIVE_KEYWORDS = [
    # ── "Hack" non-tech ──
    r"\blife\s*hack\w*\b",
    r"\bgrowth\s*hack\w*\b",
    r"\bikea\s*hack\w*\b",
    r"\bbiohack\w*\b",
    r"\btravel\s*hack\w*\b",
    r"\bfood\s*hack\w*\b",
    r"\bcareer\s*hack\w*\b",
    r"\bbody\s*hack\w*\b",
    r"\bmind\s*hack\w*\b",
    r"\bproductivity\s*hack\w*\b",
    r"\bmoney\s*hack\w*\b",
    r"\bparent\w*\s*hack\w*\b",
    r"\bhack\s+your\s+(?:life|routine|diet|morning|career|body)\b",
    r"\bsocial\s+hack(?!athon)\w*\b",
    # ── Media/piattaforme (non eventi) ──
    r"\bhackernoon\b",
    r"\bhacker\s*news\b",
    r"\bhackernews\b",
    r"\bhackaday\.com\b",
    # ── Competizioni sportive/culturali non tech ──
    r"\bconcorso\s+(?:musicale|canoro|fotografico|letterario|pittori|artistic\w+)\b",
    r"\bgara\s+(?:sportiva|ciclistica|automobilistica|calcio|nuoto|atletica)\b",
    # ── Formazione/corsi (non competizioni) ──
    r"\bcorso\s+(?:di\s+)?(?:formazione|aggiornamento|laurea|master)\b",
    r"\blezione\s+(?:di|aperta)\b",
    r"\bworkshop\s+(?:gratuito|formativo|introduttivo)\b",
    # ── Recruiting/job ──
    r"\bjob\s+fair\b",
    r"\bcareer\s+(?:fair|day|expo)\b",
    r"\brecruiting\s+(?:day|event)\b",
    r"\bassunzion[ei]\b",
    r"\boffert[ae]\s+(?:di\s+)?lavoro\b",
    # ── Recap/passato (pattern linguistici) ──
    r"\brecap\s+(?:of|del|della|dell['’]|from|20\d{2})\b",
    r"\bhighlights?\s+(?:from|of|del)\b",
    r"\bwhat\s+(?:we|I)\s+(?:learned|built)\b",
    r"\bwinners?\s+announced\b",
    r"\bvincitor[ei]\b",
    r"\brisultat[ei]\s+(?:del|della|dell)\b",
    # ── Contenuti editoriali (non annunci) ──
    r"\b(?:top|best|ultimate)\s+\d+\s+(?:hackathon|hack)\b",
    r"\bguide?\s+(?:to|for|per)\s+(?:hackathon|winning)\b",
    r"\bhow\s+to\s+(?:win|prepare|organize)\b",
    r"\btips?\s+(?:for|to|per)\s+(?:hackathon|winning|coding|your)\b",
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
