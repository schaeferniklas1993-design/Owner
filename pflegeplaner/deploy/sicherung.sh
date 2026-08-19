#!/usr/bin/env bash
# Taegliche Sicherung der Pflegeplaner-Datenbank.
# Einrichten (einmalig):
#   sudo cp /opt/pflegeplaner/deploy/sicherung.sh /opt/pflegeplaner/sicherung.sh
#   sudo chmod +x /opt/pflegeplaner/sicherung.sh
#   ( sudo crontab -l 2>/dev/null; echo '15 3 * * * /opt/pflegeplaner/sicherung.sh' ) | sudo crontab -
set -euo pipefail
ORDNER=/opt/pflegeplaner/sicherungen
mkdir -p "$ORDNER"
# .backup erzeugt eine saubere Kopie, auch waehrend die App laeuft.
sqlite3 /opt/pflegeplaner/pflegeplaner.db ".backup '$ORDNER/pflegeplaner-$(date +%F).db'"
gzip -f "$ORDNER/pflegeplaner-$(date +%F).db"
find "$ORDNER" -name 'pflegeplaner-*.db.gz' -mtime +30 -delete
