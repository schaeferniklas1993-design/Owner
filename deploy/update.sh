#!/usr/bin/env bash
# =============================================================================
# Haushaltsbuch – Ein-Klick-Update
#
# Holt den neuesten Stand aus GitHub, kopiert ihn in den laufenden App-Ordner
# (/opt/haushaltsbuch), führt die Datenbank-Migration aus und startet neu.
# Datenbank, Passwörter und Buchungen bleiben unangetastet.
#
# Aufruf (im geklonten Projektordner, z. B. ~/haushaltsbuch):
#   sudo bash deploy/update.sh
# =============================================================================
set -euo pipefail

ZIEL=/opt/haushaltsbuch
QUELLE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ $EUID -ne 0 ]]; then
    echo "FEHLER: Bitte mit sudo starten:  sudo bash deploy/update.sh"
    exit 1
fi
if [[ ! -d "$ZIEL/.venv" ]]; then
    echo "FEHLER: $ZIEL sieht nicht nach einer Installation aus."
    echo "Nutze zum Ersteinrichten:  sudo bash deploy/server-setup.sh <deine-adresse>"
    exit 1
fi

echo "==> [1/5] Neuesten Stand aus GitHub holen"
git -C "$QUELLE" pull --ff-only

echo "==> [2/5] Neue Dateien nach $ZIEL kopieren (Datenbank & Geheimnisse bleiben)"
(cd "$QUELLE" && tar --exclude .git --exclude .venv --exclude haushalt.db \
    --exclude '.secret_key' --exclude sicherungen -cf - .) | (cd "$ZIEL" && tar -xf -)

echo "==> [3/5] Abhängigkeiten prüfen"
"$ZIEL/.venv/bin/pip" install -q -r "$ZIEL/requirements.txt"

echo "==> [4/5] Datenbank-Migration"
chown -R haushalt:haushalt "$ZIEL"
sudo -u haushalt "$ZIEL/.venv/bin/python" "$ZIEL/database.py"

echo "==> [5/5] App neu starten"
systemctl restart haushaltsbuch
sleep 2
if systemctl is-active --quiet haushaltsbuch; then
    echo
    echo "============================================================"
    echo "  FERTIG! Die neue Version laeuft."
    echo "  Jetzt im Browser hart neu laden (Strg+Shift+R) bzw. die"
    echo "  Home-Bildschirm-App komplett schliessen und neu oeffnen."
    echo "============================================================"
else
    echo "FEHLER: Der Dienst laeuft nicht. Details:"
    journalctl -u haushaltsbuch -n 20 --no-pager
    exit 1
fi
