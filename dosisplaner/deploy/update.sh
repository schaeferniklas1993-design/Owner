#!/usr/bin/env bash
# "Mein Weg" aktualisieren.  Aufruf: sudo bash dosisplaner/deploy/update.sh
set -euo pipefail
ZIEL=/opt/dosisplaner
QUELLE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[[ $EUID -eq 0 ]] || { echo "FEHLER: Bitte mit sudo starten."; exit 1; }
[[ -d "$ZIEL/.venv" ]] || { echo "FEHLER: Noch nicht eingerichtet. Nutze server-setup.sh"; exit 1; }
echo "==> Programmdateien aktualisieren (Datenbank bleibt)"
(cd "$QUELLE" && tar --exclude .venv --exclude dosisplaner.db --exclude '.secret_key' \
    --exclude __pycache__ --exclude deploy --exclude sicherungen -cf - .) \
    | (cd "$ZIEL" && tar -xf -)
"$ZIEL/.venv/bin/pip" install -q -r "$ZIEL/requirements.txt"
chown -R dosis:dosis "$ZIEL"
sudo -u dosis "$ZIEL/.venv/bin/python" "$ZIEL/database.py"
systemctl restart dosisplaner
sleep 2
systemctl is-active --quiet dosisplaner \
  && echo "FERTIG! Neue Fassung laeuft." \
  || { echo "FEHLER:"; journalctl -u dosisplaner -n 20 --no-pager; exit 1; }
