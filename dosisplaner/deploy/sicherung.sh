#!/usr/bin/env bash
# Taegliche Sicherung – deine Eintraege sind persoenlich und nicht ersetzbar.
set -euo pipefail
BASIS=/opt/dosisplaner
ORDNER="$BASIS/sicherungen"
DATUM=$(date +%F)
mkdir -p "$ORDNER"
"$BASIS/.venv/bin/python" - "$BASIS/dosisplaner.db" "$ORDNER/dosisplaner-$DATUM.db" <<'PY'
import sqlite3, sys
with sqlite3.connect(sys.argv[1]) as q, sqlite3.connect(sys.argv[2]) as z:
    q.backup(z)
PY
gzip -f "$ORDNER/dosisplaner-$DATUM.db"
find "$ORDNER" -name 'dosisplaner-*.db.gz' -mtime +60 -delete
echo "Sicherung erstellt: $ORDNER/dosisplaner-$DATUM.db.gz"
