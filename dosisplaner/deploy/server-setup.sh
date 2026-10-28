#!/usr/bin/env bash
# =============================================================================
# "Mein Weg" (Dosisplaner) auf dem Server einrichten.
#
# Aufruf:  sudo bash dosisplaner/deploy/server-setup.sh meinweg.duckdns.org
#
# Wiederholbar: Datenbank und Passwort bleiben erhalten.
# Fasst keine der anderen Anwendungen an.
# =============================================================================
set -euo pipefail

ADRESSE="${1:-}"
ZIEL=/opt/dosisplaner
QUELLE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

[[ $EUID -eq 0 ]] || { echo "FEHLER: Bitte mit sudo starten."; exit 1; }
if [[ -z "$ADRESSE" ]]; then
    echo "FEHLER: Bitte die Internetadresse angeben, z. B.:"
    echo "  sudo bash dosisplaner/deploy/server-setup.sh meinweg.duckdns.org"
    exit 1
fi

echo "==> [1/7] Benutzerkonto und Ordner anlegen"
id -u dosis >/dev/null 2>&1 || useradd --system --home "$ZIEL" --shell /usr/sbin/nologin dosis
mkdir -p "$ZIEL"

echo "==> [2/7] Programmdateien kopieren (Datenbank bleibt unberührt)"
(cd "$QUELLE" && tar --exclude .venv --exclude dosisplaner.db --exclude '.secret_key' \
    --exclude __pycache__ --exclude deploy --exclude sicherungen -cf - .) \
    | (cd "$ZIEL" && tar -xf -)

echo "==> [3/7] Python-Umgebung einrichten"
apt-get install -y -qq python3-venv >/dev/null 2>&1 || {
    apt-get update -qq && apt-get install -y -qq python3-venv >/dev/null
}
[[ -d "$ZIEL/.venv" ]] || python3 -m venv "$ZIEL/.venv"
"$ZIEL/.venv/bin/pip" install -q --upgrade pip
"$ZIEL/.venv/bin/pip" install -q -r "$ZIEL/requirements.txt"

echo "==> [4/7] Datenbank anlegen bzw. aktualisieren"
chown -R dosis:dosis "$ZIEL"
sudo -u dosis "$ZIEL/.venv/bin/python" "$ZIEL/database.py"

echo "==> [5/7] Dienst einrichten"
cp "$QUELLE/deploy/dosisplaner.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable -q dosisplaner
systemctl restart dosisplaner

echo "==> [6/7] HTTPS über Caddy"
if ! grep -q "$ADRESSE" /etc/caddy/Caddyfile 2>/dev/null; then
    cat >> /etc/caddy/Caddyfile <<CADDY

$ADRESSE {
    reverse_proxy 127.0.0.1:8003
}
CADDY
    systemctl reload caddy
    echo "    Adresse $ADRESSE in Caddy eingetragen."
else
    echo "    Adresse $ADRESSE steht bereits in Caddy."
fi

echo "==> [7/7] Tägliche Sicherung einrichten"
cp "$QUELLE/deploy/sicherung.sh" "$ZIEL/sicherung.sh"
chmod +x "$ZIEL/sicherung.sh"
if ! crontab -l 2>/dev/null | grep -q "$ZIEL/sicherung.sh"; then
    ( crontab -l 2>/dev/null; echo "45 3 * * * $ZIEL/sicherung.sh" ) | crontab -
    echo "    Nächtliche Sicherung um 3:45 Uhr eingerichtet."
else
    echo "    Nächtliche Sicherung war bereits eingerichtet."
fi

sleep 2
if systemctl is-active --quiet dosisplaner; then
    echo
    echo "============================================================"
    echo "  FERTIG! 'Mein Weg' laeuft."
    echo "  Adresse:  https://$ADRESSE"
    echo "  Erstzugang: ich / start-2026"
    echo "  (Beim ersten Anmelden waehlst du dein eigenes Passwort.)"
    echo "============================================================"
else
    echo "FEHLER: Der Dienst laeuft nicht. Details:"
    journalctl -u dosisplaner -n 25 --no-pager
    exit 1
fi
