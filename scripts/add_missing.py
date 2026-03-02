#!/usr/bin/env python3
"""Aggiunge l'evento Luma mancante (perso per API error) e rigenera HTML."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from models import HackathonEvent
from storage.json_store import EventStore
from utils.html_export import generate_html

store = EventStore()

missing = HackathonEvent(
    title="The Making — Public Sharing: Creative Hackathon - The New Human (Milan)",
    url="https://lu.ma/g02myvsa",
    source="luma",
    description="Creative hackathon event in Milan as part of CODAME ART+TECH Festival 2026 — The New Human.",
    date_str="2026-03-07T13:00:00.000Z — 2026-03-07T20:00:00.000Z",
    location="TrueLayer, Via Joe Colombo, 8, 20124 Milano MI, Italia",
)
missing.is_hackathon = True
missing.confidence = 0.95

if store.is_duplicate(missing):
    print("Evento gia presente")
else:
    store.add_event(missing)
    store.save_with_timestamp("2026-03-02T21:09:49")
    print(f"Aggiunto! Totale: {store.count}")

generate_html()
print("HTML rigenerata")
