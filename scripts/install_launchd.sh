#!/usr/bin/env bash
set -euo pipefail

# Installa il plist di launchd per avviare il bot all'avvio (macOS user-level).
# Uso (da hackathon-monitor): ./scripts/install_launchd.sh

PLIST_PATH="$PWD/hackathon-monitor-bot.plist"

if [ ! -f "$PLIST_PATH" ]; then
  echo "Plist non trovato: $PLIST_PATH" >&2
  exit 2
fi

echo "Carico plist in launchd: $PLIST_PATH"
launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl load "$PLIST_PATH"
echo "Plist caricato. Usa 'launchctl list | grep hackathon.monitor.bot' per verificare." 
