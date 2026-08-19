# Fernzugriff auf den Heim-PC – RustDesk mit eigenem Server

Damit siehst und bedienst du deinen Windows-Rechner von unterwegs, als säßest
du davor. Die Vermittlung läuft über **euren eigenen Server** – die Bildschirm-
inhalte gehen also nicht über fremde Firmen-Server.

Ersetze überall `DEINE-SERVER-IP` durch die IP eures Hetzner-Servers.

---

## Vorher lesen: Dienstrechner

Auf einem Rechner, der dem Arbeitgeber gehört, ist das Installieren von
Fernwartungssoftware in vielen Einrichtungen untersagt – in der Pflege wegen
der Patientendaten meist besonders streng. **Kläre das vorher mit deiner IT
oder Leitung.** Auf deinem eigenen Handy oder Laptop ist es dagegen
unproblematisch.

Für den Fall, dass du auf einem fremden Rechner nichts installieren darfst,
gibt es die **portable Fassung** (siehe Schritt 5) – sie läuft direkt vom
USB-Stick, ohne Installation und ohne Administratorrechte.

---

## Schritt 1: Server einrichten

Per SSH auf dem Server:

```bash
sudo mkdir -p /opt/rustdesk
sudo cp ~/haushaltsbuch/deploy/rustdesk/docker-compose.yml /opt/rustdesk/
sudo nano /opt/rustdesk/docker-compose.yml
```

In der Zeile `command: hbbs -r DEINE-SERVER-IP:21117` die **echte Server-IP**
eintragen. Speichern mit `Strg+O`, Enter, `Strg+X`.

Starten:

```bash
cd /opt/rustdesk && sudo docker compose up -d
```

Prüfen (beide Dienste müssen „Up“ sein):

```bash
sudo docker compose ps
```

## Schritt 2: Ports in der Firewall öffnen

RustDesk braucht diese Ports:

```bash
sudo ufw allow 21115:21119/tcp
sudo ufw allow 21116/udp
sudo ufw reload
sudo ufw status
```

## Schritt 3: Schlüssel auslesen

Der Server erzeugt beim ersten Start einen Schlüssel. Nur wer ihn hat, darf
den Server nutzen:

```bash
sudo cat /opt/rustdesk/daten/id_ed25519.pub
```

Die ausgegebene Zeichenkette notieren – sie wird gleich gebraucht.

## Schritt 4: Heim-PC einrichten (Windows)

1. RustDesk herunterladen: https://rustdesk.com/ → Windows-Version
2. Installieren und starten
3. **⋮-Menü → Einstellungen → Netzwerk → Server (ID/Relay)**
4. Eintragen:
   - **ID-Server:** `DEINE-SERVER-IP`
   - **Relay-Server:** `DEINE-SERVER-IP`
   - **Schlüssel:** die Zeichenkette aus Schritt 3
5. Speichern
6. Unter **Einstellungen → Sicherheit** ein **festes Passwort** setzen
   (langes, eigenes Passwort – nicht das Einmalpasswort verwenden)
7. Die angezeigte **ID** notieren (9-stellige Zahl)

Damit der Zugriff jederzeit klappt:
- Unter Einstellungen **„Mit Windows starten“** aktivieren
- Im Windows-Energieplan den **Ruhezustand deaktivieren**
  (Einstellungen → System → Netzbetrieb → Energiesparmodus: „Nie“)

## Schritt 5: Zugriffsgerät einrichten

**Eigenes Handy oder eigener Laptop:**
RustDesk-App installieren (Play Store, App Store oder von rustdesk.com), unter
Einstellungen dieselben drei Angaben eintragen (ID-Server, Relay-Server,
Schlüssel). Dann ID des Heim-PCs eingeben → verbinden → Passwort eingeben.

**Fremder Rechner ohne Installationsrechte:**
Auf rustdesk.com die **portable Version** (`rustdesk-x.y.z-x86_64.exe`)
herunterladen und auf einen USB-Stick legen. Sie startet ohne Installation.
Server und Schlüssel dort einmal eintragen – die Einstellungen bleiben auf dem
Stick.

---

## Sicherheit

- **Festes Passwort** setzen (Schritt 4.6) und niemandem weitergeben.
  Ohne Passwort kommt niemand auf den Rechner, selbst wenn er die ID kennt.
- Der Schlüssel aus Schritt 3 sorgt dafür, dass nur eure eigenen Geräte
  diesen Server benutzen können.
- Die Verbindung ist Ende-zu-Ende verschlüsselt.
- Auf dem Heim-PC zeigt RustDesk während einer Sitzung ein Hinweisfenster –
  so fällt sofort auf, wenn jemand unerwartet verbunden ist.
- Wenn du RustDesk längere Zeit nicht brauchst, beende es auf dem Heim-PC.

## Ressourcen

Die beiden Dienste brauchen zusammen etwa **20–30 MB Arbeitsspeicher**. Der
Server hat davon reichlich – Haushaltsbuch, Vaultwarden, Pflegeplaner und
RustDesk zusammen liegen bei rund 15 % Auslastung.

## Wenn etwas hakt

| Problem | Prüfen |
|---|---|
| Verbindung kommt nicht zustande | `sudo docker compose -f /opt/rustdesk/docker-compose.yml logs --tail 40` |
| Dienste laufen nicht | `cd /opt/rustdesk && sudo docker compose ps` |
| Ports zu? | `sudo ufw status` – 21115–21119/tcp und 21116/udp müssen offen sein |
| „Schlüssel ungültig“ | Schlüssel aus Schritt 3 erneut auslesen und exakt kopieren |
| PC nicht erreichbar | Läuft der Heim-PC? Schläft er? Ist RustDesk gestartet? |

## Aktualisieren

```bash
cd /opt/rustdesk && sudo docker compose pull && sudo docker compose up -d
```
