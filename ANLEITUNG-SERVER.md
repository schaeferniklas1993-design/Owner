# Anleitung: Haushaltsbuch auf einem günstigen Server – Nutzung vom Handy

Ziel: Das Haushaltsbuch läuft rund um die Uhr auf einem kleinen Mietserver,
und ihr beide nutzt es von euren iPhones aus – von überall, verschlüsselt
per HTTPS, wie eine normale App auf dem Home-Bildschirm.

**Kosten: ca. 3–4 € im Monat.** Ihr braucht einmalig etwa eine Stunde Zeit
und einen PC/Laptop für die Einrichtung (danach läuft alles ohne PC).

---

## Schritt 1: Server mieten (~ 3,50 €/Monat)

Empfehlung: **Hetzner Cloud** (deutscher Anbieter, Rechenzentrum in
Deutschland/Finnland, minutengenaue Abrechnung, jederzeit kündbar).

1. Konto anlegen auf https://console.hetzner.cloud
2. **Neues Projekt** anlegen (z. B. „Haushaltsbuch“), dann **Server hinzufügen**:
   - Standort: Nürnberg oder Falkenstein
   - Abbild (Image): **Ubuntu 24.04**
   - Typ: der kleinste reicht dicke – z. B. **CAX11** (Arm, 2 Kerne, 4 GB RAM)
     oder **CX22**; beide um die 3,50 €/Monat
   - Bei „SSH-Schlüssel“: wenn ihr keinen habt, einfach weglassen –
     Hetzner schickt euch dann ein Root-Passwort per E-Mail
3. Server erstellen. Nach ~1 Minute seht ihr seine **IP-Adresse**
   (z. B. `203.0.113.45`) – die braucht ihr gleich zweimal.

Alternativen, falls gewünscht: IONOS VPS (ab 1 €/Monat), Netcup (~3 €/Monat).
Die Schritte darunter sind identisch, sobald ihr ein Ubuntu mit Root-Zugang habt.

## Schritt 2: Kostenlose Internet-Adresse holen (DuckDNS)

Eine feste Adresse statt der nackten IP – und Voraussetzung für HTTPS:

1. Auf https://www.duckdns.org mit Google/GitHub anmelden (kostenlos)
2. Eine Subdomain anlegen, z. B. `haushalt-mustermann` →
   eure Adresse ist dann `haushalt-mustermann.duckdns.org`
3. Bei „current ip“ die **IP-Adresse eures Servers** eintragen und speichern

(Wer mag, kauft stattdessen eine eigene Domain für ~5 €/Jahr – funktioniert genauso.)

## Schritt 3: Mit dem Server verbinden

Am PC/Laptop ein Terminal öffnen (Windows: PowerShell) und einloggen –
IP durch eure ersetzen:

```bash
ssh root@203.0.113.45
```

Beim ersten Mal mit „yes“ bestätigen; das Passwort kam per E-Mail von Hetzner
(ihr müsst es beim ersten Login ändern).

## Schritt 4: Grundeinrichtung und Firewall

Alles am Stück einfügbar:

```bash
apt update && apt -y upgrade
apt -y install git python3-venv python3-pip ufw

# Firewall: nur SSH und Web-Verkehr erlauben
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# Eigener Benutzer, unter dem die App läuft (nicht als root!)
adduser --system --group --home /opt/haushaltsbuch haushalt
```

## Schritt 5: App auf den Server holen

Da das Repository privat ist, braucht ihr ein GitHub-Token:
GitHub → Settings → Developer settings → **Personal access tokens →
Fine-grained tokens** → Token nur für dieses Repository mit Berechtigung
„Contents: Read-only“ erstellen.

```bash
cd /opt
git clone https://DEIN_GITHUB_TOKEN@github.com/schaeferniklas1993-design/Owner.git haushaltsbuch-code
cp -r haushaltsbuch-code/. /opt/haushaltsbuch/ && rm -rf haushaltsbuch-code

cd /opt/haushaltsbuch
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Datenbank anlegen und alles dem App-Benutzer übergeben
sudo -u haushalt .venv/bin/python database.py
chown -R haushalt:haushalt /opt/haushaltsbuch
```

## Schritt 6: App als Dauerdienst starten

Die fertige Dienstdatei liegt im Repository:

```bash
cp /opt/haushaltsbuch/deploy/haushaltsbuch.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now haushaltsbuch
systemctl status haushaltsbuch    # muss "active (running)" zeigen
```

Ab jetzt startet die App automatisch mit – auch nach einem Server-Neustart.

## Schritt 7: HTTPS mit Caddy (automatisches Zertifikat)

Caddy nimmt die Anfragen aus dem Internet an, holt sich selbstständig ein
kostenloses Let's-Encrypt-Zertifikat und leitet an die App weiter:

```bash
apt -y install debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
apt update && apt -y install caddy

# Vorlage übernehmen und EURE DuckDNS-Adresse eintragen:
cp /opt/haushaltsbuch/deploy/Caddyfile /etc/caddy/Caddyfile
nano /etc/caddy/Caddyfile     # haushalt-mustermann.duckdns.org ersetzen
systemctl reload caddy
```

Test: Am PC oder Handy `https://haushalt-mustermann.duckdns.org` öffnen –
die Anmeldeseite muss mit Schloss-Symbol erscheinen.

## Schritt 8: Absichern und Gehälter einrichten

**Sofort die Startpasswörter ändern** – die App hängt jetzt im Internet:

```bash
cd /opt/haushaltsbuch
sudo -u haushalt .venv/bin/python cli.py passwort niklas
sudo -u haushalt .venv/bin/python cli.py passwort partnerin
```

Gehälter setzen (buchen dann automatisch am 15. bzw. 1.):

```bash
sudo -u haushalt .venv/bin/python cli.py gehalt niklas 2450,00
sudo -u haushalt .venv/bin/python cli.py gehalt partnerin 2100,00
```

## Schritt 9: Auf beiden iPhones einrichten

1. In Safari `https://haushalt-mustermann.duckdns.org` öffnen
2. Anmelden (du als `niklas`, deine Frau als `partnerin`)
3. **Teilen-Symbol → „Zum Home-Bildschirm“** – fertig: eigenes 💶-Icon,
   startet im Vollbild, fühlt sich an wie eine App

## Schritt 10: Tägliche Sicherung (empfohlen)

```bash
crontab -u haushalt -e
```

Diese Zeile eintragen (Sicherung jede Nacht um 3 Uhr in `sicherungen/`):

```
0 3 * * * cd /opt/haushaltsbuch && .venv/bin/python cli.py sicherung
```

Hetzner bietet zusätzlich automatische Server-Backups für ~20 % Aufpreis
(~0,80 €/Monat) – ein Klick in der Hetzner-Konsole, lohnt sich.

---

## Später aktualisieren

Wenn es eine neue Version der App gibt:

```bash
cd /opt/haushaltsbuch
sudo -u haushalt git pull
.venv/bin/pip install -r requirements.txt
systemctl restart haushaltsbuch
```

## Wenn etwas nicht läuft

| Problem | Prüfen mit |
|---|---|
| Seite lädt nicht | `systemctl status haushaltsbuch` und `systemctl status caddy` |
| App-Fehler ansehen | `journalctl -u haushaltsbuch -n 50` |
| Kein HTTPS-Zertifikat | Stimmt die IP bei DuckDNS? `journalctl -u caddy -n 50` |
| Passwort vergessen | `sudo -u haushalt .venv/bin/python cli.py passwort niklas` |

## Kostenübersicht

| Posten | Kosten |
|---|---|
| Hetzner CAX11/CX22 | ~3,50 €/Monat |
| DuckDNS-Adresse | kostenlos |
| HTTPS-Zertifikat (Let's Encrypt) | kostenlos |
| Optional: Hetzner-Backups | ~0,80 €/Monat |
| **Gesamt** | **~3,50–4,30 €/Monat** |
