# Vaultwarden (Passwort-Manager) auf demselben Server einrichten

Vaultwarden ist ein leichter, voll Bitwarden-kompatibler Passwort-Server. Er
läuft neben dem Haushaltsbuch, HTTPS liefert euer vorhandenes Caddy. Alle
offiziellen Bitwarden-Apps/Erweiterungen funktionieren – ihr tragt dort nur
eure eigene Server-Adresse ein.

Ersetze überall `haushalt-vault.duckdns.org` durch eure echte Adresse und
`DEINE-IP` durch die Server-IP.

---

## Schritt 1: Zweite kostenlose Adresse anlegen (DuckDNS)

Bitwarden-Apps brauchen eine eigene Adresse mit HTTPS.

1. https://www.duckdns.org → anmelden
2. Neue Subdomain anlegen, z. B. `haushalt-vault` → `haushalt-vault.duckdns.org`
3. Bei „current ip“ die **IP eures Servers** eintragen → „update ip“

(Ein Konto darf mehrere DuckDNS-Domains haben – die zeigen einfach auf dieselbe IP.)

## Schritt 2: Docker installieren (falls noch nicht vorhanden)

Per SSH auf dem Server:

```bash
curl -fsSL https://get.docker.com | sh
```

Prüfen: `docker --version` zeigt eine Versionsnummer.

## Schritt 3: Vaultwarden-Dateien an ihren Platz legen

Die Konfiguration liegt im Haushaltsbuch-Repo. Kopiere sie nach `/opt/vaultwarden`:

```bash
sudo mkdir -p /opt/vaultwarden
sudo cp ~/haushaltsbuch/deploy/vaultwarden/docker-compose.yml /opt/vaultwarden/
sudo nano /opt/vaultwarden/docker-compose.yml    # DOMAIN auf eure Adresse ändern
```

(Speichern in nano: `Strg+O`, Enter, `Strg+X`.)

## Schritt 4: Vaultwarden starten

```bash
cd /opt/vaultwarden && sudo docker compose up -d
```

Test lokal: `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8081`
→ `200` bedeutet, der Dienst läuft.

## Schritt 5: HTTPS über Caddy freischalten

Die Adresse zu Caddy hinzufügen:

```bash
sudo nano /etc/caddy/Caddyfile
```

Als **zweiten Block** unter den vorhandenen anfügen (eigene Adresse einsetzen):

```
haushalt-vault.duckdns.org {
    reverse_proxy 127.0.0.1:8081
}
```

Dann neu laden:

```bash
sudo systemctl reload caddy
```

## Schritt 6: Konten anlegen und dann abriegeln

1. Im Browser `https://haushalt-vault.duckdns.org` öffnen → **Konto erstellen**
   (du und Mäuschen je ein eigenes Konto). Das **Master-Passwort** ist der
   Schlüssel zu allem – lang, einmalig, und **niemals** vergessen: Es wird
   serverseitig nicht gespeichert, ohne es sind die Daten unwiederbringlich weg.
2. Danach die Registrierung schließen: in
   `/opt/vaultwarden/docker-compose.yml` `SIGNUPS_ALLOWED` auf `"false"`
   setzen, dann:
   ```bash
   cd /opt/vaultwarden && sudo docker compose up -d
   ```
3. In der Bitwarden-App/Erweiterung **2-Faktor-Authentifizierung** aktivieren.

## Schritt 7: In den Bitwarden-Apps eintragen

In jeder offiziellen Bitwarden-App (iPhone, Android, Browser-Erweiterung):
**Einstellungen / Region → „Selbst gehostet“** → Server-URL
`https://haushalt-vault.duckdns.org` → dann mit euren Konten anmelden.

## Schritt 8: Backup (Pflicht!)

Die Daten liegen in `/opt/vaultwarden/vw-data`. Tägliche Sicherung einrichten:

```bash
sudo crontab -e
```

Diese Zeile anfügen (sichert jede Nacht um 3:30 Uhr):

```
30 3 * * * tar -czf /opt/vaultwarden/backup-$(date +\%F).tar.gz -C /opt/vaultwarden vw-data && find /opt/vaultwarden -name 'backup-*.tar.gz' -mtime +14 -delete
```

Noch besser: diese Backup-Dateien zusätzlich außer Haus kopieren (z. B. auf
eine Hetzner Storage Box oder gelegentlich per `scp` auf euren PC) – dann
übersteht ihr sogar einen Totalverlust des Servers.

---

## Updates

```bash
cd /opt/vaultwarden && sudo docker compose pull && sudo docker compose up -d
```

## Wenn etwas hakt

| Problem | Prüfen |
|---|---|
| Seite lädt nicht | `sudo docker compose -f /opt/vaultwarden/docker-compose.yml logs --tail 40` |
| Kein HTTPS | Zeigt `haushalt-vault` bei DuckDNS auf die Server-IP? `journalctl -u caddy -n 30` |
| App verbindet nicht | Server-URL exakt `https://…` (mit https), Konto vorhanden? |

## Sicherheitshinweise

- Der Passwort-Tresor ist euer wertvollstes Ziel – **HTTPS ist Pflicht**
  (habt ihr über Caddy), Backups sind Pflicht, Master-Passwort niemals verlieren.
- `SIGNUPS_ALLOWED` nach dem Anlegen auf `"false"` – sonst könnte jeder, der die
  Adresse kennt, ein Konto anlegen.
- Firewall: Port 8081 ist bewusst nur auf `127.0.0.1` – von außen kommt man
  ausschließlich verschlüsselt über Caddy (Port 443) rein. Nichts extra öffnen.
