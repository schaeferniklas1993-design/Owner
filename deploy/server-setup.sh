#!/usr/bin/env bash
# =============================================================================
# Haushaltsbuch – automatische Server-Einrichtung
#
# Richtet einen frischen Ubuntu-Server (22.04/24.04) komplett ein:
# Firewall, App-Benutzer, Python-Umgebung, Datenbank, Autostart (systemd),
# HTTPS (Caddy + Let's Encrypt) und tägliche Datenbank-Sicherung.
#
# Aufruf als root im geklonten Projektordner:
#   sudo bash deploy/server-setup.sh haushalt-mustermann.duckdns.org
# =============================================================================
set -euo pipefail

ZIEL=/opt/haushaltsbuch

if [[ $EUID -ne 0 ]]; then
    echo "FEHLER: Bitte als root ausführen:  sudo bash deploy/server-setup.sh <adresse>"
    exit 1
fi

DOMAIN="${1:-}"
while [[ -z "$DOMAIN" ]]; do
    read -rp "Eure Internet-Adresse (z. B. haushalt-mustermann.duckdns.org): " DOMAIN
done

QUELLE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo
echo "Haushaltsbuch wird eingerichtet:"
echo "  Quelle:  $QUELLE"
echo "  Ziel:    $ZIEL"
echo "  Adresse: https://$DOMAIN"
echo

echo "==> [1/9] Pakete installieren"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -yq python3-venv python3-pip ufw curl gnupg \
    fail2ban unattended-upgrades \
    debian-keyring debian-archive-keyring apt-transport-https

echo "==> [2/9] Firewall aktivieren (nur SSH, HTTP, HTTPS offen)"
ufw allow OpenSSH >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw --force enable

echo "==> [3/9] App-Benutzer anlegen und Dateien kopieren"
id -u haushalt >/dev/null 2>&1 || adduser --system --group --home "$ZIEL" haushalt
mkdir -p "$ZIEL"
if [[ "$QUELLE" != "$ZIEL" ]]; then
    (cd "$QUELLE" && tar --exclude .git --exclude .venv -cf - .) | (cd "$ZIEL" && tar -xf -)
fi

echo "==> [4/9] Python-Umgebung und Datenbank"
python3 -m venv "$ZIEL/.venv"
"$ZIEL/.venv/bin/pip" install -q -r "$ZIEL/requirements.txt"
chown -R haushalt:haushalt "$ZIEL"
sudo -u haushalt "$ZIEL/.venv/bin/python" "$ZIEL/database.py"

echo "==> [5/9] Autostart-Dienst einrichten (systemd)"
cp "$ZIEL/deploy/haushaltsbuch.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now haushaltsbuch
sleep 2
systemctl is-active --quiet haushaltsbuch || {
    echo "FEHLER: Der App-Dienst läuft nicht. Details: journalctl -u haushaltsbuch -n 30"
    exit 1
}

echo "==> [6/9] Caddy installieren (HTTPS mit automatischem Zertifikat)"
if ! command -v caddy >/dev/null; then
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
        | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
        > /etc/apt/sources.list.d/caddy-stable.list
    apt-get update -q
    apt-get install -yq caddy
fi
printf '%s {\n    reverse_proxy 127.0.0.1:8000\n}\n' "$DOMAIN" > /etc/caddy/Caddyfile
systemctl enable --now caddy
systemctl reload caddy

echo "==> [7/9] Tägliche Datenbank-Sicherung um 3 Uhr nachts"
( crontab -u haushalt -l 2>/dev/null | grep -v "cli.py sicherung" || true
  echo "0 3 * * * cd $ZIEL && .venv/bin/python cli.py sicherung" ) | crontab -u haushalt -

echo "==> [8/9] Server-Härtung (fail2ban, Auto-Updates, SSH)"
# fail2ban sperrt IP-Adressen nach wiederholten SSH-Fehlversuchen automatisch.
systemctl enable --now fail2ban

# Ubuntu-Sicherheitsupdates installieren sich künftig von selbst.
printf 'APT::Periodic::Update-Package-Lists "1";\nAPT::Periodic::Unattended-Upgrade "1";\n' \
    > /etc/apt/apt.conf.d/20auto-upgrades

# SSH-Passwort-Login abschalten – aber nur, wenn ein SSH-Key hinterlegt ist,
# sonst würde man sich selbst aussperren.
if [[ -s /root/.ssh/authorized_keys ]]; then
    printf 'PasswordAuthentication no\nPermitRootLogin prohibit-password\n' \
        > /etc/ssh/sshd_config.d/99-haushaltsbuch.conf
    systemctl reload ssh 2>/dev/null || systemctl reload sshd 2>/dev/null || true
    echo "    SSH-Key gefunden – Passwort-Login per SSH ist jetzt deaktiviert."
else
    echo "    HINWEIS: Kein SSH-Key hinterlegt – SSH-Passwort-Login bleibt aktiv."
    echo "    (Empfehlung: SSH-Key einrichten, dann dieses Skript erneut ausführen.)"
fi

echo "==> [9/9] Selbsttest"
STATUS=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/login || true)
if [[ "$STATUS" == "200" ]]; then
    echo "    App antwortet lokal: OK"
else
    echo "    WARNUNG: App antwortet lokal mit Status '$STATUS'."
    echo "    Details: journalctl -u haushaltsbuch -n 30"
fi

echo
echo "============================================================"
echo "  FERTIG! Das Haushaltsbuch läuft."
echo
echo "  Web-Adresse:   https://$DOMAIN"
echo "  (Das HTTPS-Zertifikat holt Caddy beim ersten Aufruf automatisch –"
echo "   das kann 1–2 Minuten dauern. Voraussetzung: Die Adresse zeigt"
echo "   bei DuckDNS auf die IP dieses Servers.)"
echo
echo "  Passwörter: Beim ersten Login am Handy fragt die App automatisch"
echo "  nach einem eigenen Passwort (niklas/niklas-start bzw."
echo "  maeuschen/maeuschen-start)."
echo
echo "  Und die Gehälter eintragen (Beispielbeträge ersetzen):"
echo "    sudo -u haushalt $ZIEL/.venv/bin/python $ZIEL/cli.py gehalt niklas 2450,00"
echo "    sudo -u haushalt $ZIEL/.venv/bin/python $ZIEL/cli.py gehalt maeuschen 2100,00"
echo "============================================================"
