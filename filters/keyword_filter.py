"""
Pre-filtro keyword per ridurre le chiamate al LLM.

Logica:
1. Se il testo contiene una keyword negativa → SCARTA (sicuramente non hackathon)
2. Se il testo contiene SOLO anni passati (es. 2024, 2023) → SCARTA (evento passato)
3. Se il testo contiene una keyword positiva → PASSA al LLM (probabile hackathon)
4. Se nessun match → SCARTA (risparmia le limitate chiamate LLM free tier)

Le keyword usano regex con word boundary (\b) per evitare falsi positivi.
"""

import re
import logging
from datetime import datetime

import config
from models import HackathonEvent

logger = logging.getLogger(__name__)

# Compila i pattern una sola volta
_positive_patterns = [re.compile(p, re.IGNORECASE) for p in config.POSITIVE_KEYWORDS]
_negative_patterns = [re.compile(p, re.IGNORECASE) for p in config.NEGATIVE_KEYWORDS]
_year_pattern = re.compile(r'\b(20[0-9]{2})\b')

# URL che sicuramente NON sono pagine evento
_JUNK_URL_PATTERNS = [
    # Social media
    re.compile(r"linkedin\.com/(posts|pulse)/", re.I),
    re.compile(r"facebook\.com/(photos|posts|watch|reel|story)", re.I),
    re.compile(r"instagram\.com/p/", re.I),
    re.compile(r"(twitter|x)\.com/.+/status/", re.I),
    re.compile(r"youtube\.com/watch", re.I),
    # Profili utente (Devpost, GitHub, ecc.)
    re.compile(r"devpost\.com/[A-Za-z0-9_-]+(/[a-z]+)?/?$", re.I),  # profili e sotto-pagine
    re.compile(r"/users?/[^/]+/?$", re.I),
    # Pagine di listing/ricerca/directory (non evento singolo)
    re.compile(r"eventbrite\.[a-z]+/d/", re.I),
    re.compile(r"eventbrite\.[a-z]+/b/", re.I),          # browse categories
    re.compile(r"eventbrite\.[a-z]+/organizer/", re.I),   # organizer pages
    re.compile(r"allhackathons\.com/", re.I),
    re.compile(r"hackathon\.com/city/", re.I),            # listing per città
    re.compile(r"allevents\.in/", re.I),
    re.compile(r"stayhappening\.com/", re.I),
    re.compile(r"itch\.io/jams", re.I),                   # listing game jams
    re.compile(r"ctftime\.org/?$", re.I),                 # homepage CTF
    re.compile(r"hackthedate\.com/?$", re.I),             # homepage calendar
    # Pagine tag/categoria/archivio (non evento singolo)
    re.compile(r"/tag/[^/]+", re.I),                      # qualsiasi /tag/xxx
    re.compile(r"/event-category/", re.I),                # categorie eventi
    re.compile(r"/category/", re.I),                      # categorie generiche
    # Homepage organizzazioni (non evento singolo)
    re.compile(r"fondazionetriulza\.org/?$", re.I),
    re.compile(r"techstars\.com/communities/", re.I),
    re.compile(r"fi\.co/insight/", re.I),
    re.compile(r"smau\.it/.*/Events$", re.I),
    re.compile(r"iniziativa\.cc/", re.I),
    re.compile(r"cyberchallenge\.it/(en/)?(students|workshop)", re.I),
    # Wiki
    re.compile(r"wiki.*/Main_Page", re.I),
    re.compile(r"wiki.*/Pagina_principale", re.I),
    re.compile(r"wikipedia\.org/wiki/", re.I),
    re.compile(r"mediawiki\.org/wiki/", re.I),
    re.compile(r"/wiki/.+/(zh|nl|es|fr|de|ja|ko|pt|ru|ar|hi|he|pl|sv|da|ca|fi|no|cs|sk|hu|ro|tr|uk|vi|id|th|bn|ms)$", re.I),
    re.compile(r"/wiki/.+/Participants", re.I),
    re.compile(r"wiki\.wikimedia\.it/wiki/(Diario|Wikimedia_news)", re.I),
    re.compile(r"planet\.wikimedia\.org", re.I),
    re.compile(r"foss\.events/", re.I),
    # News / blog / articoli (non pagina evento)
    re.compile(r"/news[_-]?(it|en|es)?/", re.I),
    re.compile(r"/blog/", re.I),
    re.compile(r"/magazine/", re.I),
    re.compile(r"/articoli?/", re.I),
    re.compile(r"businesspeople\.it/", re.I),
    re.compile(r"startupbusiness\.it/", re.I),
    re.compile(r"wired\.it/", re.I),
    re.compile(r"ilsole24ore\.com/", re.I),
    re.compile(r"corriere\.it/", re.I),
    re.compile(r"repubblica\.it/", re.I),
    re.compile(r"atmosferamag\.it/", re.I),
    re.compile(r"cagliaripost\.com/", re.I),
    re.compile(r"gioconews\.it/", re.I),
    re.compile(r"gamespress\.com/", re.I),
    re.compile(r"meridiananotizie\.it/", re.I),
    re.compile(r"analyticsinsight\.net/", re.I),
    # Forum / community / Q&A
    re.compile(r"forum\.freecodecamp\.org/", re.I),
    re.compile(r"meetup\.com/[^/]+/?$", re.I),            # meetup group pages (non eventi)
    # Documenti
    re.compile(r"\.(pdf|doc|docx|ppt|pptx)(\?|$)", re.I),
    re.compile(r"codemotion\.com/magazine", re.I),
    re.compile(r"ninjamarketing\.it/", re.I),
    re.compile(r"uomoemanager\.it/", re.I),
    # Siti generici non-evento
    re.compile(r"welcometothejungle\.com/", re.I),
    re.compile(r"makerbot\.com/", re.I),
    re.compile(r"citadel\.com/careers/", re.I),
    re.compile(r"yourinspirationweb\.com/", re.I),
    re.compile(r"daryo\.uz/", re.I),
    re.compile(r"gazeta\.uz/", re.I),
    re.compile(r"centralasian\.uz/", re.I),
    # Homepage/listing siti globali
    re.compile(r"globalgamejam\.org/?$", re.I),
    re.compile(r"globalgamejam\.org/jam-sites/\d{4}/?$", re.I),  # listing sedi (non sede singola)
    re.compile(r"globalgamejam\.it/?$", re.I),                     # homepage IGDA Italy
    re.compile(r"meetup\.com/topics/", re.I),                      # topic listing
    re.compile(r"pretix\.eu/", re.I),                              # ticketing (non pagina evento)
]


def _is_junk_url(url: str) -> bool:
    """URL chiaramente non una pagina evento."""
    return any(p.search(url) for p in _JUNK_URL_PATTERNS)


def _is_past_event(text: str) -> bool:
    """Verifica se l'evento è chiaramente nel passato.

    Regole:
    - Se il testo contiene almeno un anno e TUTTI gli anni trovati sono < anno corrente → passato
    - Se il testo contiene l'anno corrente o futuro → NON passato (anche se ha anni vecchi)
    - Se il testo non contiene nessun anno → NON passato (lascio decidere al LLM)
    """
    current_year = datetime.now().year
    years = [int(m) for m in _year_pattern.findall(text)]

    if not years:
        return False  # Nessun anno → non posso giudicare, passa al LLM

    # Se c'è almeno un anno >= corrente, non è passato
    if any(y >= current_year for y in years):
        return False

    # Tutti gli anni trovati sono passati
    return True


def keyword_filter(event: HackathonEvent) -> bool:
    """Applica il pre-filtro keyword a un evento.

    Returns:
        True → l'evento deve passare al LLM (o potrebbe essere un hackathon).
        False → l'evento è sicuramente NON un hackathon (keyword negativa matchata).
    """
    text = f"{event.title} {event.description}".strip()

    # Step 0: URL rumorosi → scarta subito
    if event.url and _is_junk_url(event.url):
        logger.info("Scartato per URL non-evento: %s — %s", event.title[:60], event.url[:80])
        return False

    # Step 1: keyword negative → scarta con certezza
    for pattern in _negative_patterns:
        if pattern.search(text):
            logger.debug("Keyword negativa matchata per: %s", event.title)
            return False

    # Step 2: anno passato → scarta (es. "Hackathon Milano 2024" a febbraio 2026)
    if _is_past_event(text):
        logger.info("Scartato evento passato: %s", event.title)
        return False

    # Step 3: keyword positive → passa al LLM
    for pattern in _positive_patterns:
        if pattern.search(text):
            logger.debug("Keyword positiva matchata per: %s", event.title)
            return True

    # Step 4: nessun match → SCARTA
    logger.debug("Nessuna keyword matchata per: %s (scartato)", event.title)
    return False


def keyword_filter_batch(events: list[HackathonEvent]) -> tuple[list[HackathonEvent], int]:
    """Applica il filtro a una lista di eventi.

    Returns:
        Tupla (eventi_che_passano, conteggio_scartati).
    """
    passed = []
    discarded = 0

    for event in events:
        if keyword_filter(event):
            passed.append(event)
        else:
            discarded += 1
            logger.info("Scartato da keyword filter: %s", event.title)

    return passed, discarded
