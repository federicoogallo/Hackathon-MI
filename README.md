# 🏆 Hackathon Milano Monitor

Aggregatore automatico di eventi hackathon a Milano da 8+ fonti eterogenee.  
Filtra con LLM (Groq · Llama 3.3 70B, gratuito), notifica via Telegram Bot, avviabile in locale o su GitHub Actions.

---

## Architettura

```
Collectors (8 fonti in parallelo)
        │
        ▼
  Deduplicazione (SHA256 URL + fuzzy titolo SequenceMatcher > 0.85)
        │
        ▼
  Pre-filtro Keyword (regex word-boundary: scarta "growth hacking", "biohacking"…)
        │
        ▼
  Filtro LLM (Groq · Llama 3.3 70B, batch da 20, few-shot, threshold 0.7)
        │
        ▼
  Notifica Telegram (nuovo hackathon + report giornaliero)
        │
        ▼
  Salvataggio storico (data/events.json)
```

### Collector registrati

| # | Fonte | Metodo | Note |
|---|-------|--------|------|
| 1 | **Eventbrite** | REST API | Richiede `EVENTBRITE_API_KEY` |
| 2 | **Google CSE** | Custom Search API | Meta-aggregatore: copre LinkedIn, Meetup, Twitter indirettamente. Richiede `GOOGLE_CSE_API_KEY` + `GOOGLE_CSE_CX` |
| 3 | **InnovUp** | HTML scraping | innovup.net/eventi |
| 4 | **Luma** | `__NEXT_DATA__` JSON + HTML fallback | lu.ma |
| 5 | **Devpost** | HTML scraping | Bassa copertura per Milano |
| 6 | **PoliHub** | HTML scraping | Bloccato da WAF (coperto indirettamente da Google CSE) |
| 7 | **Università** | HTML scraping | PoliMi, Bocconi, Bicocca (parser indipendenti) |
| 8 | **Reddit** | PRAW (API ufficiale) | r/ItalyInformatica + r/italy. Richiede `REDDIT_CLIENT_ID` + `REDDIT_CLIENT_SECRET` |

---

## Setup locale

### 1. Clona e crea il virtual environment

```bash
git clone <repo-url>
cd hackathon-monitor

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configura le API key

```bash
cp .env.example .env
```

Edita `.env` con le tue chiavi. **Nessuna chiave è obbligatoria** — i collector senza chiave vengono silenziosamente saltati:

| Variabile | Come ottenerla |
|-----------|---------------|
| `EVENTBRITE_API_KEY` | [eventbrite.com/platform/api](https://www.eventbrite.com/platform/api) → crea un'app → copia il Private token |
| `GOOGLE_CSE_API_KEY` | [console.cloud.google.com](https://console.cloud.google.com/) → APIs & Services → Credentials → Create API Key → abilita "Custom Search JSON API" |
| `GOOGLE_CSE_CX` | [programmablesearchengine.google.com](https://programmablesearchengine.google.com/) → crea un motore di ricerca → copia l'ID (cx) |
| `GROQ_API_KEY` | [console.groq.com](https://console.groq.com/) → API Keys → Create (gratuito, nessuna carta richiesta) |
| `REDDIT_CLIENT_ID` | [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps) → crea "script" app → copia l'ID sotto il nome |
| `REDDIT_CLIENT_SECRET` | Stessa pagina Reddit → copia il "secret" |
| `TELEGRAM_BOT_TOKEN` | Parla con [@BotFather](https://t.me/BotFather) su Telegram → `/newbot` → copia il token |
| `TELEGRAM_CHAT_ID` | Invia un messaggio al bot, poi visita `https://api.telegram.org/bot<TOKEN>/getUpdates` → prendi `chat.id` |

### 3. Esegui

```bash
# Dry-run (nessuna notifica, solo log)
python main.py --dry-run

# Run completo (con notifiche Telegram)
python main.py
```

### 4. Test

```bash
python -m pytest tests/ -v
```

---

## Deploy su GitHub Actions

### 1. Fork/push il repository

### 2. Configura i Secrets

Vai su **Settings → Secrets and variables → Actions → New repository secret** e aggiungi tutte le chiavi dal `.env`.

### 3. Abilita il workflow

Il workflow si trova in `.github/workflows/check_hackathons.yml`:
- **Cron**: ogni giorno alle 9:00 CET (`0 8 * * *` UTC)
- **Manuale**: dal tab "Actions" → "Run workflow"
- Auto-commit di `data/events.json` con tutto lo storico

---

## Bot Telegram

`bot.py` espone un bot in long-polling con i comandi:

| Comando | Descrizione |
|---------|-------------|
| `/scan` | Avvia una scansione manuale |
| `/eventi` | Hackathon futuri confermati, ordinati per data |
| `/report` | Dettaglio ultima scansione (pipeline + contatori) |
| `/status` | Statistiche dello storico |
| `/fonti` | Sorgenti monitorate |
| `/help` | Lista comandi |

Avvio locale (attiva `.venv` e lancia `python bot.py`):

```bash
./scripts/start_bot.sh
```

Avvio automatico all'accesso macOS (launchd):

```bash
./scripts/install_launchd.sh
```

Accessibile solo dal `TELEGRAM_CHAT_ID` configurato — tutti gli altri messaggi ricevono un rifiuto automatico.

---

## Come aggiungere un nuovo collector

1. Crea `collectors/mio_collector.py`:

```python
from models import BaseCollector, HackathonEvent

class MioCollector(BaseCollector):
    @property
    def name(self) -> str:
        return "mio_collector"

    def collect(self) -> list[HackathonEvent]:
        # Scraping/API qui
        return [
            HackathonEvent(
                title="...",
                url="...",
                source=self.name,
            )
        ]
```

2. Registralo in `main.py` → `get_collectors()`:

```python
from collectors.mio_collector import MioCollector

def get_collectors():
    return [
        # ... esistenti ...
        MioCollector(),
    ]
```

3. Aggiungi un test in `tests/test_collectors.py`.

---

## Struttura del progetto

```
hackathon-monitor/
├── main.py                  # Orchestratore pipeline
├── config.py                # Configurazione centralizzata
├── models.py                # HackathonEvent, BaseCollector
├── requirements.txt
├── .env.example
├── .gitignore
├── collectors/
│   ├── eventbrite.py
│   ├── google_cse.py
│   ├── innovup.py
│   ├── luma.py
│   ├── devpost.py
│   ├── polihub.py
│   ├── universities.py
│   └── reddit.py
├── filters/
│   ├── keyword_filter.py    # Pre-filtro regex
│   └── llm_filter.py        # Groq · Llama 3.3 70B classifier
├── notifiers/
│   └── telegram.py          # Bot Telegram
├── storage/
│   └── json_store.py        # Persistenza + dedup 2 livelli
├── utils/
│   └── http.py              # HTTP client con retry/backoff
├── data/
│   └── events.json          # Storico eventi (auto-generato)
├── tests/
│   ├── test_models.py
│   ├── test_storage.py
│   ├── test_filters.py
│   ├── test_collectors.py
│   └── test_pipeline.py
└── .github/
    └── workflows/
        └── check_hackathons.yml
```

---

## Limiti noti

- **PoliHub**: bloccato da WAF/Cloudflare (403). Coperto indirettamente da Google CSE.
- **Twitter/X**: API Free Tier è write-only. Coperto indirettamente da Google CSE (`site:twitter.com`).
- **LinkedIn**: nessuna API pubblica per eventi. Coperto da Google CSE (`site:linkedin.com/events`).
- **Google CSE**: quota gratuita 100 query/giorno (sufficiente per 1 run/giorno con 8 query).
- **Groq free tier**: 14.400 req/giorno, 30 RPM. Senza `GROQ_API_KEY` il filtro LLM viene saltato (solo keyword filter).

---

## Licenza

MIT
