#!/usr/bin/env bash
# Pflegeplaner aktualisieren – holt den neuen Stand und startet neu.
# Aufruf:  sudo bash pflegeplaner/deploy/update.sh
set -euo pipefail
ZIEL=/opt/pflegeplaner
QUELLE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

[[ $EUID -eq 0 ]] || { echo "FEHLER: Bitte mit sudo starten."; exit 1; }
[[ -d "$ZIEL/.venv" ]] || { echo "FEHLER: Noch nicht eingerichtet. Nutze server-setup.sh"; exit 1; }

echo "==> Programmdateien aktualisieren (Datenbank bleibt)"
(cd "$QUELLE" && tar --exclude .venv --exclude pflegeplaner.db --exclude '.secret_key' \
    --exclude __pycache__ --exclude deploy -cf - .) | (cd "$ZIEL" && tar -xf -)
"$ZIEL/.venv/bin/pip" install -q -r "$ZIEL/requirements.txt"
chown -R pflege:pflege "$ZIEL"
sudo -u pflege "$ZIEL/.venv/bin/python" "$ZIEL/database.py"
systemctl restart pflegeplaner
sleep 2
systemctl is-active --quiet pflegeplaner \
  && echo "FERTIG! Neue Fassung laeuft." \
  || { echo "FEHLER:"; journalctl -u pflegeplaner -n 20 --no-pager; exit 1; }
