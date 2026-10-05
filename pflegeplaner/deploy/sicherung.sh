#!/usr/bin/env bash
# Taegliche Sicherung der Pflegeplaner-Datenbank.
#
# Das Setup-Skript richtet diese Sicherung bereits ein (naechtlich um 3:15 Uhr,
# 30 Tage Aufbewahrung). Manuell starten:  sudo /opt/pflegeplaner/sicherung.sh
set -euo pipefail

BASIS=/opt/pflegeplaner
ORDNER="$BASIS/sicherungen"
DATUM=$(date +%F)
mkdir -p "$ORDNER"

# Pythons eingebautes sqlite3 nutzen – so wird kein Extra-Paket gebraucht.
# .backup erzeugt eine in sich stimmige Kopie, auch waehrend die App laeuft.
"$BASIS/.venv/bin/python" - "$BASIS/pflegeplaner.db" "$ORDNER/pflegeplaner-$DATUM.db" <<'PY'
import sqlite3, sys
quelle, ziel = sys.argv[1], sys.argv[2]
with sqlite3.connect(quelle) as q, sqlite3.connect(ziel) as z:
    q.backup(z)
PY

gzip -f "$ORDNER/pflegeplaner-$DATUM.db"
find "$ORDNER" -name 'pflegeplaner-*.db.gz' -mtime +30 -delete
echo "Sicherung erstellt: $ORDNER/pflegeplaner-$DATUM.db.gz"
