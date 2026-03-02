Avvio automatico del bot
========================

Due opzioni per avviare il bot senza digitare manualmente i comandi:

1) Avvio manuale rapido (usando lo script)

Esegui dalla cartella `hackathon-monitor`:

```bash
./scripts/start_bot.sh
```

Lo script attiva `.venv` e lancia `python bot.py`.

2) Avvio automatico all'avvio macOS (launchd)

Se vuoi che il bot sia sempre in esecuzione e si avvii all'accesso utente, carica il plist con:

```bash
./scripts/install_launchd.sh
```

Questo esegue `launchctl load hackathon-monitor-bot.plist` per l'utente corrente.

Nota: entrambi gli script non modificano privilegi di sistema. Se preferisci usare systemd/servizio Linux, modifica `hackathon-monitor-bot.service` e usa `systemctl`.
