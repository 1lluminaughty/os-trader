#!/bin/bash
# Live-Sync: Watch ~/Downloads/OS_trader and rsync changes to home server.
# Use: ./watch-deploy.sh
#
# Requires: fswatch (brew install fswatch) and SSH-key auth.
#
# Streamlit auf dem Server hat --server.runOnSave=true und --fileWatcherType=poll,
# d.h. sobald die rsync'te Datei dort landet, lädt sich das Dashboard automatisch
# innerhalb von 1-2 Sekunden neu.

set -e

SRC="$HOME/Downloads/OS_trader/"
DEST="mathias@192.168.178.42:~/os-trader/"

sync() {
    rsync -av --delete-after \
        --exclude='.venv' --exclude='__pycache__' --exclude='.claude' \
        --exclude='watch-deploy.sh' --exclude='*.swp' --exclude='.DS_Store' \
        --include='*.py' --include='*.yml' --include='*.txt' --include='Dockerfile' \
        --include='.dockerignore' --include='README.md' \
        "$SRC" "$DEST" 2>&1 | grep -vE '^(sending|sent|total|building)'
}

echo "[$(date +%H:%M:%S)] Initial sync..."
sync

echo "[$(date +%H:%M:%S)] Watching $SRC — drück Strg+C zum Beenden"
fswatch -o -l 1 \
    --exclude='\.venv' --exclude='__pycache__' --exclude='\.git' \
    --exclude='\.DS_Store' --exclude='\.swp$' \
    "$SRC" | while read -r _; do
    echo "[$(date +%H:%M:%S)] Änderung erkannt, syncen..."
    sync
done
