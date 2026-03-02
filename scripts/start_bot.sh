#!/usr/bin/env bash
set -euo pipefail

# Avvia il bot usando la virtualenv locale (.venv) nella cartella padre.
# Uso: ./scripts/start_bot.sh

cd "$(dirname "$0")/.."

if [ ! -f ".venv/bin/activate" ]; then
  echo "Virtualenv non trovata in .venv — crea l'ambiente e installa le dipendenze prima." >&2
  exit 2
fi

echo "Attivo virtualenv e avvio bot..."
# shellcheck disable=SC1091
source .venv/bin/activate

exec python bot.py
