#!/usr/bin/env bash
# =============================================================================
# Pflegeplaner auf dem Server einrichten.
#
# Aufruf (im geklonten Projektordner):
#   sudo bash pflegeplaner/deploy/server-setup.sh pflege-team.duckdns.org
#
# Das Skript ist wiederholbar: Datenbank und Passwörter bleiben erhalten.
# Es fasst weder das Haushaltsbuch noch Vaultwarden an.
# =============================================================================
set -euo pipefail

ADRESSE="${1:-}"
ZIEL=/opt/pflegeplaner
QUELLE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ $EUID -ne 0 ]]; then
    echo "FEHLER: Bitte mit sudo starten."
    exit 1
fi
if [[ -z "$ADRESSE" ]]; then
    echo "FEHLER: Bitte die Internetadresse angeben, z. B.:"
    echo "  sudo bash pflegeplaner/deploy/server-setup.sh pflege-team.duckdns.org"
    exit 1
fi

echo "==> [1/6] Benutzerkonto und Ordner anlegen"
id -u pflege >/dev/null 2>&1 || useradd --system --home "$ZIEL" --shell /usr/sbin/nologin pflege
mkdir -p "$ZIEL"

echo "==> [2/6] Programmdateien kopieren (Datenbank bleibt unberührt)"
(cd "$QUELLE" && tar --exclude .venv --exclude pflegeplaner.db --exclude '.secret_key' \
    --exclude __pycache__ --exclude deploy -cf - .) | (cd "$ZIEL" && tar -xf -)

echo "==> [3/6] Python-Umgebung einrichten"
apt-get install -y -qq python3-venv >/dev/null
[[ -d "$ZIEL/.venv" ]] || python3 -m venv "$ZIEL/.venv"
"$ZIEL/.venv/bin/pip" install -q --upgrade pip
"$ZIEL/.venv/bin/pip" install -q -r "$ZIEL/requirements.txt"

echo "==> [4/6] Datenbank anlegen bzw. aktualisieren"
chown -R pflege:pflege "$ZIEL"
sudo -u pflege "$ZIEL/.venv/bin/python" "$ZIEL/database.py"

echo "==> [5/6] Dienst einrichten"
cp "$QUELLE/deploy/pflegeplaner.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable -q pflegeplaner
systemctl restart pflegeplaner

echo "==> [6/6] HTTPS über Caddy"
if ! grep -q "$ADRESSE" /etc/caddy/Caddyfile 2>/dev/null; then
    cat >> /etc/caddy/Caddyfile <<EOF

$ADRESSE {
    reverse_proxy 127.0.0.1:8002
}
EOF
    systemctl reload caddy
    echo "    Adresse $ADRESSE in Caddy eingetragen."
else
    echo "    Adresse $ADRESSE steht bereits in Caddy."
fi

sleep 2
if systemctl is-active --quiet pflegeplaner; then
    echo
    echo "============================================================"
    echo "  FERTIG! Der Pflegeplaner laeuft."
    echo "  Adresse:  https://$ADRESSE"
    echo "  Erstzugang: leitung / start-2026"
    echo "  (Das Passwort muss bei der ersten Anmeldung geaendert werden.)"
    echo "============================================================"
else
    echo "FEHLER: Der Dienst laeuft nicht. Details:"
    journalctl -u pflegeplaner -n 25 --no-pager
    exit 1
fi
