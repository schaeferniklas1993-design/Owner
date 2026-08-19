# Pflegeplaner – Einrichtung Schritt für Schritt

Kalender, Visiten und Übergaben fürs Pflegeteam. Läuft auf demselben Server wie
das Haushaltsbuch, stört es aber nicht: eigene Adresse, eigener Dienst, eigene
Datenbank, eigener Systembenutzer.

Ersetze überall `DEINE-IP` durch die Server-IP und `pflege-team.duckdns.org`
durch eure echte Adresse.

---

## Vorab: Datenschutz klären

Termine wie „Herr Meier, 10 Uhr Zahnarzt“ sind **Gesundheitsdaten** und nach
DSGVO besonders geschützt (Art. 9). Verantwortlich ist die Einrichtung, nicht
du als Privatperson.

**Vor dem Einsatz mit echten Namen** kurz mit Leitung und Datenschutz\-
beauftragtem sprechen. Was hilfreich ist, wenn du dort vorstellst:

| Frage | Antwort |
|---|---|
| Wo liegen die Daten? | Auf einem Server in Deutschland (Hetzner), nicht bei einem US-Dienst |
| Wer kommt ran? | Nur angemeldete Teammitglieder, jeder mit eigenem Zugang |
| Verschlüsselt? | Ja, HTTPS auf dem gesamten Weg |
| Passwörter? | Nur als nicht rückrechenbarer Prüfwert gespeichert |
| Löschbar? | Ja, jeder Eintrag einzeln; Bewohner werden ausgeblendet statt gelöscht |
| Sicherung? | Tägliches Backup, 30 Tage Aufbewahrung |

Zum Ausprobieren mit erfundenen Namen ist all das nicht nötig.

---

## Schritt 1: Adresse anlegen (DuckDNS)

1. https://www.duckdns.org → anmelden
2. Neue Subdomain anlegen, z. B. `pflege-team` → `pflege-team.duckdns.org`
3. Bei „current ip“ die **IP eures Servers** eintragen → „update ip“

## Schritt 2: Auf den Server

```bash
ssh root@DEINE-IP
```

## Schritt 3: Neuen Stand holen

```bash
cd ~/haushaltsbuch && git pull
```

Der Pflegeplaner liegt im Unterordner `pflegeplaner/` desselben Projekts.

## Schritt 4: Einrichten (ein Befehl)

```bash
sudo bash ~/haushaltsbuch/pflegeplaner/deploy/server-setup.sh pflege-team.duckdns.org
```

Das Skript legt alles an: Systembenutzer, Programmordner unter
`/opt/pflegeplaner`, Python-Umgebung, Datenbank, Dienst und den HTTPS-Eintrag
in Caddy. Am Ende steht:

```
FERTIG! Der Pflegeplaner laeuft.
Adresse:  https://pflege-team.duckdns.org
Erstzugang: leitung / start-2026
```

## Schritt 5: Erste Anmeldung

1. `https://pflege-team.duckdns.org` im Browser öffnen
2. Anmelden mit **leitung** / **start-2026**
3. Sofort ein eigenes Passwort wählen (wird verlangt)

## Schritt 6: Grunddaten anlegen

In dieser Reihenfolge geht es am schnellsten:

1. **Bewohner** → Namen, Zimmer, Wohnbereich eintragen
2. **Visiten** → Ärzte und Therapeuten mit Telefon und festem Visitentag
3. **Kalender** → jetzt lassen sich Termine mit Auswahl aus beiden Listen anlegen

## Schritt 7: Zugänge fürs Team

Unter **Team** (nur für die Rolle „Leitung“ sichtbar):

1. Anzeigename, Benutzername und Startpasswort eintragen
2. Rolle wählen: *Pflege* (normal) oder *Leitung* (darf Zugänge verwalten)
3. Startpasswort weitergeben – beim ersten Anmelden muss es geändert werden

## Schritt 8: Tägliche Sicherung einrichten

```bash
sudo cp /opt/pflegeplaner/deploy/sicherung.sh /opt/pflegeplaner/sicherung.sh
sudo chmod +x /opt/pflegeplaner/sicherung.sh
( sudo crontab -l 2>/dev/null; echo '15 3 * * * /opt/pflegeplaner/sicherung.sh' ) | sudo crontab -
```

Prüfen: `sudo crontab -l` – dort muss die Zeile stehen.
Einmal testen: `sudo /opt/pflegeplaner/sicherung.sh && ls -lh /opt/pflegeplaner/sicherungen`

**Zusätzlich dringend empfohlen:** In der Hetzner-Konsole beim Server
**Backups aktivieren** (~0,75 €/Monat). Das sichert den kompletten Server
täglich – die einzige Absicherung gegen einen Serverdefekt.

## Schritt 9: Als App aufs Handy

Auf jedem Diensthandy oder privaten Gerät:

- **Android (Chrome):** Adresse öffnen → ⋮-Menü → **App installieren**
- **iPhone (Safari):** Adresse öffnen → Teilen-Knopf → **Zum Home-Bildschirm**

Danach liegt der Kalender als eigenes Symbol auf dem Startbildschirm.

---

## Später: aktualisieren

```bash
cd ~/haushaltsbuch && git pull
sudo bash ~/haushaltsbuch/pflegeplaner/deploy/update.sh
```

Unten auf jeder Seite steht die laufende Version – daran erkennst du sofort,
ob der neue Stand aktiv ist.

## Wenn etwas hakt

| Problem | Befehl |
|---|---|
| Seite lädt nicht | `systemctl status pflegeplaner --no-pager` |
| Fehlermeldungen ansehen | `journalctl -u pflegeplaner -n 40 --no-pager` |
| HTTPS klemmt | `journalctl -u caddy -n 30 --no-pager` |
| Passwort vergessen | Über einen anderen Leitungs-Zugang zurücksetzen |
| Alle Leitungs-Passwörter weg | siehe unten |

**Notfall – Leitungspasswort zurücksetzen** (direkt auf dem Server):

```bash
sudo -u pflege /opt/pflegeplaner/.venv/bin/python -c "
import sys; sys.path.insert(0, '/opt/pflegeplaner')
import database
from werkzeug.security import generate_password_hash
c = database.verbinden()
c.execute('UPDATE benutzer SET passwort_hash = ?, passwort_neu = 1 WHERE benutzername = ?',
          (generate_password_hash('neustart-2026'), 'leitung'))
c.commit(); print('Passwort von leitung gesetzt auf: neustart-2026')
"
```

---

## Was die Anwendung kann

**Kalender** – Wochenansicht Montag bis Sonntag, beliebig weit vor und zurück
(2026 und 2027 sind abgedeckt). Termine mit Uhrzeit oder ganztägig, verknüpft
mit Bewohner und Arzt, mit Notizfeld. Abhaken, bearbeiten, löschen. Der heutige
Tag ist hervorgehoben. Der Wochentag wird automatisch berechnet – kein Rätseln,
auf welchen Tag ein Datum fällt.

**Visiten** – Verzeichnis der Ärzte und Therapeuten mit Fachrichtung, Telefon
(am Handy direkt anrufbar), festem Visitentag und Hinweisfeld. Darüber die
anstehenden Visiten und Arzttermine der nächsten 14 Tage auf einen Blick.

**Übergaben** – pro Tag und Schicht (Früh/Spät/Nacht). Eintrag wahlweise
allgemein oder zu einer bestimmten Person, Wichtiges farbig hervorgehoben.
Mit Verfasser und Uhrzeit. Tagweise blätterbar.

**Bewohner** – Liste mit Zimmer, Wohnbereich und Hinweis. Beim Auszug wird
niemand gelöscht, sondern nur ausgeblendet, damit frühere Einträge lesbar
bleiben.

**Team** – Zugänge anlegen, Passwörter zurücksetzen, Zugänge sperren.
