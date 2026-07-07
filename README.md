# Haushaltsbuch

Gemeinsames Ein- und Ausgaben-Buch für zwei Personen mit eigener Datenbank,
zwei Zugängen, drei Claude-Agents und einer Web-Oberfläche.

## Überblick

| Baustein | Datei(en) | Zweck |
|---|---|---|
| Datenbank | `database.py` → `haushalt.db` (SQLite) | Benutzer, Kategorien, Buchungen, Daueraufträge |
| Web-Oberfläche | `app.py`, `templates/`, `static/` | Login, Dashboard mit Diagrammen, Buchungen, Daueraufträge |
| Kommandozeile | `cli.py` | Buchen und Auswerten ohne Browser – das Werkzeug der Agents |
| Agents | `.claude/agents/` | `finanzagent-niklas`, `finanzagent-partnerin`, `haushaltsanalyst` |

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
| `partnerin` | `partnerin-start` | am **1.** des Monats |

**Wichtig:** Startpasswörter nach der ersten Anmeldung ändern:

```bash
python3 cli.py passwort niklas
python3 cli.py passwort partnerin
```

## Gehälter einrichten

Die Gehalts-Daueraufträge existieren bereits, sind aber inaktiv, bis ein Betrag
gesetzt ist – entweder in der Web-Oberfläche unter **Daueraufträge** oder per CLI:

```bash
python3 cli.py gehalt niklas 2450,00      # bucht ab sofort jeden 15. automatisch
python3 cli.py gehalt partnerin 2100,00   # bucht ab sofort jeden 1. automatisch
```

Fällige Daueraufträge werden bei jedem Aufruf von Web-App oder CLI automatisch
nachgebucht (auch rückwirkend bis zu 12 Monate) – pro Monat genau einmal.

## Die drei Agents

Die Agents liegen in `.claude/agents/` und stehen in Claude Code automatisch
zur Verfügung, sobald dieses Projekt geöffnet ist:

- **finanzagent-niklas** – bucht Einnahmen/Ausgaben ausschließlich für Niklas.
- **finanzagent-partnerin** – bucht ausschließlich für die Partnerin.
- **haushaltsanalyst** – wertet den gesamten Haushalt aus (Berichte, Sparquote,
  größte Ausgabenposten), bucht aber selbst nichts.

Beispiele: *„Buche 54,30 € Lebensmittel für Niklas“* ·
*„Buche 32,90 € Restaurant für die Partnerin“* ·
*„Wie steht der Haushalt diesen Monat da?“*

## CLI-Referenz

```bash
python3 cli.py --benutzer niklas ausgabe 54,30 --kategorie Lebensmittel --beschreibung "Wocheneinkauf"
python3 cli.py --benutzer partnerin einnahme 80,00 --kategorie Geschenk --datum 2026-07-10
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

## Fernzugriff (beide von unterwegs)

`app.py` lauscht auf allen Netzwerk-Schnittstellen (`0.0.0.0`, Port 5000).
Im Heimnetz reicht also `http://<IP-des-Rechners>:5000`. Für Zugriff von
außerhalb empfiehlt sich ein VPN (z. B. WireGuard/Tailscale) statt einer
direkten Portfreigabe – die Anmeldung schützt die Daten, aber ein VPN schützt
den ganzen Dienst.
