# Haushaltsbuch

Gemeinsames Ein- und Ausgaben-Buch für zwei Personen mit eigener Datenbank,
zwei Zugängen, drei Claude-Agents und einer Web-Oberfläche.

## Überblick

| Baustein | Datei(en) | Zweck |
|---|---|---|
| Datenbank | `database.py` → `haushalt.db` (SQLite) | Benutzer, Kategorien, Buchungen, Daueraufträge |
| Web-Oberfläche | `app.py`, `templates/`, `static/` | Login, Dashboard mit Diagrammen, Buchungen, Daueraufträge |
| Kommandozeile | `cli.py` | Buchen und Auswerten ohne Browser – das Werkzeug der Agents |
| Agents | `.claude/agents/` | `finanzagent-niklas`, `finanzagent-maeuschen`, `haushaltsanalyst` |

## Schnellstart

```bash
pip install -r requirements.txt
python3 app.py
# → http://localhost:5000
```

Beim ersten Start wird `haushalt.db` automatisch angelegt – inklusive der
beiden Zugänge und der Gehalts-Daueraufträge.

## Die zwei Zugänge

| Benutzername | Startpasswort | Gehalt (Dauerauftrag) |
|---|---|---|
| `niklas` | `niklas-start` | am **15.** des Monats (Mitte des Monats) |
| `maeuschen` | `maeuschen-start` | am **1.** des Monats |

**Beim ersten Login** fragt die App jeden Benutzer automatisch nach einem
eigenen neuen Passwort (mindestens 8 Zeichen) – erst danach geht es ins
Dashboard. iPhone/Browser bieten dabei an, das Passwort zu speichern.
Später ändern: Menüpunkt **„Passwort“** in der App oder
`python3 cli.py passwort <benutzername>`.

## Gehälter einrichten

Die Gehalts-Daueraufträge existieren bereits, sind aber inaktiv, bis ein Betrag
gesetzt ist – entweder in der Web-Oberfläche unter **Daueraufträge** oder per CLI:

```bash
python3 cli.py gehalt niklas 2450,00      # bucht ab sofort jeden 15. automatisch
python3 cli.py gehalt maeuschen 2100,00   # bucht ab sofort jeden 1. automatisch
```

Fällige Daueraufträge werden bei jedem Aufruf von Web-App oder CLI automatisch
nachgebucht (auch rückwirkend bis zu 12 Monate) – pro Monat genau einmal.

## Die drei Agents

Die Agents liegen in `.claude/agents/` und stehen in Claude Code automatisch
zur Verfügung, sobald dieses Projekt geöffnet ist:

- **finanzagent-niklas** – bucht Einnahmen/Ausgaben ausschließlich für Niklas.
- **finanzagent-maeuschen** – bucht ausschließlich für die Mäuschen.
- **haushaltsanalyst** – wertet den gesamten Haushalt aus (Berichte, Sparquote,
  größte Ausgabenposten), bucht aber selbst nichts.

Beispiele: *„Buche 54,30 € Lebensmittel für Niklas“* ·
*„Buche 32,90 € Restaurant für die Mäuschen“* ·
*„Wie steht der Haushalt diesen Monat da?“*

## CLI-Referenz

```bash
python3 cli.py --benutzer niklas ausgabe 54,30 --kategorie Lebensmittel --beschreibung "Wocheneinkauf"
python3 cli.py --benutzer maeuschen einnahme 80,00 --kategorie Geschenk --datum 2026-07-10
python3 cli.py --benutzer niklas uebersicht --monat 2026-07   # Monatsübersicht einer Person
python3 cli.py bericht --monat 2026-07                        # Haushaltsbericht beider Personen
python3 cli.py kategorien                                     # alle Kategorien
python3 cli.py dauerauftraege                                 # alle Daueraufträge
python3 cli.py gehalt niklas 2450,00                          # Gehalt setzen/ändern
python3 cli.py passwort niklas                                # Passwort ändern
python3 cli.py sicherung                                      # Sicherungskopie nach sicherungen/
```

Beträge können deutsch (`1.234,56`) oder mit Punkt (`1234.56`) eingegeben werden.

## Datenhaltung & Sicherung

- Alle Beträge werden als **Cent (Ganzzahl)** gespeichert – keine Rundungsfehler.
- Die Datenbank `haushalt.db` liegt bewusst **nicht** im Repository
  (siehe `.gitignore`), damit eure Finanzdaten privat bleiben.
- Für lange Haltbarkeit: regelmäßig `python3 cli.py sicherung` ausführen –
  die Kopien landen datiert im Ordner `sicherungen/`.

## Nutzung am iPhone

Die App läuft nicht auf dem iPhone selbst, sondern auf einem Rechner zu Hause –
das iPhone bedient sie über Safari (beide Handys teilen sich so dieselbe Datenbank):

1. App auf einem dauerhaft laufenden Rechner starten (PC, Mini-PC, Raspberry Pi, NAS):
   `python3 app.py`
2. IP-Adresse des Rechners im Heimnetz herausfinden (z. B. `192.168.1.20`).
3. Am iPhone in Safari öffnen: `http://192.168.1.20:5000` und anmelden.
4. In Safari **Teilen → „Zum Home-Bildschirm“** wählen – das Haushaltsbuch
   erscheint dann mit eigenem Icon wie eine normale App und startet im Vollbild.
5. Für Zugriff außerhalb des WLANs: **Tailscale** (kostenlos) auf dem Rechner und
   beiden iPhones installieren – danach funktioniert die App von überall über die
   Tailscale-Adresse des Rechners, ohne Portfreigabe im Router.

## Fernzugriff (beide von unterwegs)

Zwei Wege:

1. **Eigener Mietserver (~3,50 €/Monat), von überall erreichbar** –
   Schritt-für-Schritt-Anleitung in **[ANLEITUNG-SERVER.md](ANLEITUNG-SERVER.md)**
   (Hetzner + DuckDNS + HTTPS via Caddy + Autostart per systemd).
2. **Rechner zu Hause + VPN**: `app.py` lauscht auf allen Schnittstellen
   (`0.0.0.0`, Port 5000); im Heimnetz reicht `http://<IP-des-Rechners>:5000`,
   von unterwegs per Tailscale/WireGuard – ohne Portfreigabe im Router.
