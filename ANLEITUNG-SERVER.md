# Schritt-für-Schritt: Haushaltsbuch auf einem günstigen Cloud-Server

**Das Ziel:** Das Haushaltsbuch läuft Tag und Nacht auf einem kleinen
Mietserver (~3,50 €/Monat). Du und deine Frau öffnet es auf euren iPhones
wie eine normale App – von überall, verschlüsselt per HTTPS.

**Das Gute:** Die gesamte Server-Konfiguration erledigt ein mitgeliefertes
Skript (`deploy/server-setup.sh`) automatisch. Deine Aufgabe ist nur:
Server anklicken, Adresse anlegen, drei Befehle einfügen.

**Du brauchst:** ~30 Minuten, eine Kreditkarte oder PayPal für den
Server-Anbieter, einen PC oder Laptop für die Einrichtung (nur einmalig).

---

## Teil 1: Server mieten bei Hetzner (~10 Minuten)

Hetzner ist ein deutscher Anbieter, Server stehen in Deutschland,
monatlich kündbar, Abrechnung minutengenau.

1. Öffne https://accounts.hetzner.com/signUp und **registriere dich**
   (E-Mail + Passwort, danach Identität/Bezahlmethode bestätigen –
   PayPal oder Karte).
2. Öffne die **Cloud Console**: https://console.hetzner.cloud
3. Klicke auf **„+ Neues Projekt“**, nenne es `Haushaltsbuch`, öffne es.
4. Klicke auf den roten Knopf **„Server hinzufügen“** und wähle:
   - **Standort:** Falkenstein oder Nürnberg (egal welcher)
   - **Image:** Ubuntu **24.04**
   - **Typ:** „Shared vCPU“ → **CX22** (2 vCPU, 4 GB RAM, ~3,79 €/Monat)
     – oder **CAX11** (Arm) falls angeboten, der ist noch etwas günstiger.
     Beide sind für diese App massiv überdimensioniert, kleiner geht nicht.
   - **Netzwerk:** Haken bei „Öffentliche IPv4“ MUSS gesetzt sein
   - **SSH-Schlüssel:** überspringen (dann bekommst du ein Passwort per Mail)
   - Alles andere: Standardwerte lassen
   - **Name** unten: `haushaltsbuch`
5. Klicke **„Kostenpflichtig erstellen“**. Nach ~1 Minute ist der Server da.
6. **Notiere die IP-Adresse** des Servers – sie steht groß in der
   Server-Übersicht, z. B. `203.0.113.45`.
7. Hetzner schickt dir eine **E-Mail mit dem Root-Passwort** – gleich griffbereit halten.

> 💡 Optional, aber empfohlen: In der Server-Ansicht unter **„Backups“**
> die automatischen Backups aktivieren (+20 %, also ~0,80 €/Monat).
> Damit kann selbst ein kaputter Server einfach zurückgespielt werden.

## Teil 2: Kostenlose Internet-Adresse anlegen (~5 Minuten)

Statt der IP-Nummer bekommt ihr eine merkbare Adresse – und die ist
Voraussetzung für das HTTPS-Zertifikat.

1. Öffne https://www.duckdns.org und melde dich oben mit Google oder
   GitHub an (kostenlos, keine Registrierung nötig).
2. Im Feld unter **„domains“** einen Namen eintragen, z. B.
   `haushalt-niklas` → Klick auf **„add domain“**.
   Eure Adresse ist dann: **`haushalt-niklas.duckdns.org`**
3. In der Zeile eurer neuen Domain ins Feld **„current ip“** die
   **IP-Adresse des Hetzner-Servers** eintragen (aus Teil 1, Punkt 6)
   → Klick auf **„update ip“**.

Fertig. Die Adresse zeigt jetzt auf euren Server.

## Teil 3: Mit dem Server verbinden (~5 Minuten)

**Windows:** Startmenü → „PowerShell“ öffnen.
**Mac:** Programme → Dienstprogramme → „Terminal“.

Dort eintippen (deine Server-IP einsetzen) und Enter:

```
ssh root@203.0.113.45
```

- Frage `Are you sure you want to continue connecting?` → `yes` tippen, Enter.
- `password:` → das Root-Passwort aus der Hetzner-E-Mail eingeben
  (man sieht beim Tippen nichts – das ist normal), Enter.
- Beim ersten Login verlangt der Server, das Passwort zu ändern:
  erst das alte nochmal, dann zweimal ein neues eigenes.
  **Das neue Passwort gut aufbewahren!**

Du bist drin, wenn links `root@haushaltsbuch:~#` steht.

## Teil 4: App installieren – drei Befehle (~10 Minuten)

**Befehl 1 – GitHub-Token bereitlegen** (weil euer Repository privat ist):

1. Im Browser: https://github.com/settings/personal-access-tokens/new
2. Name: `haushaltsbuch-server` · Expiration: `No expiration`
3. „Repository access“: **Only select repositories** → `Owner` auswählen
4. „Permissions“ → „Repository permissions“ → **Contents: Read-only**
5. **„Generate token“** klicken und den Token (beginnt mit `github_pat_…`) kopieren.

**Befehl 2 – App herunterladen** (im schwarzen Server-Fenster, Token einsetzen):

```bash
git clone -b claude/household-budget-tracker-r23vrn https://DEIN_TOKEN@github.com/schaeferniklas1993-design/Owner.git haushaltsbuch
```

> Falls dieser Stand inzwischen in den Hauptzweig übernommen wurde,
> einfach das `-b claude/…` weglassen.

**Befehl 3 – alles automatisch einrichten** (eure DuckDNS-Adresse einsetzen):

```bash
cd haushaltsbuch && sudo bash deploy/server-setup.sh haushalt-niklas.duckdns.org
```

Das Skript läuft 2–4 Minuten und erledigt selbstständig:

| Schritt | Was passiert |
|---|---|
| Firewall | Nur SSH und Web-Verkehr bleiben offen |
| App-Benutzer | Die App läuft unter einem eigenen Benutzer, nicht als root |
| Python + Datenbank | Umgebung wird gebaut, `haushalt.db` mit euren zwei Zugängen angelegt |
| Autostart | systemd-Dienst: App startet automatisch, auch nach Server-Neustart |
| HTTPS | Caddy wird installiert und holt das Zertifikat von Let's Encrypt selbst |
| Sicherung | Jede Nacht um 3 Uhr automatische Datenbank-Kopie nach `sicherungen/` |
| Härtung | fail2ban gegen SSH-Angriffe, automatische Sicherheitsupdates, SSH-Passwort-Login aus (sofern SSH-Key hinterlegt) |

Am Ende meldet es `FERTIG!` und zeigt die nächsten Befehle an.

## Teil 5: Gehälter eintragen (~2 Minuten)

**Passwörter braucht ihr hier nicht mehr zu setzen:** Beim ersten Login am
Handy fragt die App jeden von euch automatisch nach einem eigenen neuen
Passwort (Anmeldung zunächst mit `niklas` / `niklas-start` bzw.
`maeuschen` / `maeuschen-start`, dann erscheint die Passwort-wählen-Seite).
Das iPhone bietet danach an, das Passwort im Schlüsselbund zu speichern.

Noch im Server-Fenster die echten Netto-Gehälter eintragen – sie buchen ab
dann automatisch, deins am 15., das deiner Frau am 1. des Monats:

```bash
sudo -u haushalt /opt/haushaltsbuch/.venv/bin/python /opt/haushaltsbuch/cli.py gehalt niklas 2450,00
sudo -u haushalt /opt/haushaltsbuch/.venv/bin/python /opt/haushaltsbuch/cli.py gehalt maeuschen 2100,00
```

Mit `exit` vom Server abmelden. Die Einrichtung am PC ist damit beendet –
der Server läuft ab jetzt allein.

## Teil 6: Auf beiden iPhones einrichten (~2 Minuten)

Auf **deinem** iPhone und dem **deiner Frau**:

1. Safari öffnen → `https://haushalt-niklas.duckdns.org` (eure Adresse)
   – die Anmeldeseite muss mit **Schloss-Symbol** erscheinen.
   (Direkt nach der Einrichtung kann das Zertifikat 1–2 Minuten brauchen.)
2. Anmelden: du als `niklas` (Startpasswort `niklas-start`), deine Frau als
   `maeuschen` (Startpasswort `maeuschen-start`).
3. Die App fragt jetzt automatisch: **eigenes neues Passwort wählen**
   (mindestens 8 Zeichen), speichern – und die iPhone-Frage
   „Passwort sichern?“ mit **Ja** beantworten, dann ist es im Schlüsselbund.
4. **Teilen-Knopf** (Quadrat mit Pfeil) → **„Zum Home-Bildschirm“** → „Hinzufügen“.

Fertig! Das Haushaltsbuch liegt jetzt mit 💶-Icon auf beiden Home-Bildschirmen,
startet im Vollbild und ihr seht beide dieselben Daten – live.

---

## Später: App aktualisieren

Wenn es eine neue Version gibt, per SSH einloggen und **beide** Befehle ausführen:

```bash
cd ~/haushaltsbuch && git pull
sudo bash deploy/server-setup.sh haushalt-niklas.duckdns.org
```

**Wichtig – der zweite Befehl ist Pflicht, nicht optional:** Der Klon liegt in
`~/haushaltsbuch`, die *laufende* App aber in `/opt/haushaltsbuch`. `git pull`
allein aktualisiert nur den Klon; erst das Setup-Skript kopiert die neuen Dateien
nach `/opt`, führt die Datenbank-Migration aus und startet den Dienst neu. Ein
bloßes `git pull && systemctl restart` lädt weiterhin die alte Version.

(Das Skript ist wiederholbar – Datenbank, Passwörter und Buchungen bleiben
erhalten, weil die Datenbank separat in `/opt/haushaltsbuch` liegt und nicht
überschrieben wird.)

Danach im Browser einmal hart neu laden (**Strg+Shift+R**) bzw. die
Home-Bildschirm-App komplett schließen und neu öffnen, sonst zeigt der
Browser-Zwischenspeicher noch die alte Ansicht.

## Wenn etwas nicht läuft

| Problem | Lösung |
|---|---|
| Seite lädt gar nicht | `systemctl status haushaltsbuch caddy` – beides muss „active“ sein |
| Fehlermeldungen der App | `journalctl -u haushaltsbuch -n 50` |
| Kein Schloss/Zertifikatsfehler | Zeigt DuckDNS wirklich auf die Server-IP? Dann `journalctl -u caddy -n 50` |
| Passwort vergessen | Teil-5-Befehl einfach erneut ausführen |
| Alles kaputt | Hetzner-Backup zurückspielen oder Server löschen und Teil 3–5 wiederholen (Sicherung aus `sicherungen/` vorher kopieren) |

## Kosten im Überblick

| Posten | Kosten |
|---|---|
| Hetzner CX22/CAX11 | ~3,50–3,80 €/Monat |
| DuckDNS-Adresse | kostenlos |
| HTTPS-Zertifikat (Let's Encrypt) | kostenlos |
| Optional: Hetzner-Backups | ~0,80 €/Monat |
| **Gesamt** | **~3,50–4,60 €/Monat** |
