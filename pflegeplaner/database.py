"""Datenbank des Pflegeplaners: Anlegen, Verbinden, Hilfsfunktionen.

Alle Daten liegen in einer einzigen SQLite-Datei neben diesem Skript.
Aufruf zum Anlegen/Aktualisieren:  python3 database.py
"""
import datetime
import os
import sqlite3

from werkzeug.security import generate_password_hash

BASIS_VERZEICHNIS = os.path.dirname(os.path.abspath(__file__))
DATENBANK = os.path.join(BASIS_VERZEICHNIS, "pflegeplaner.db")

# Schichten für Übergaben – Reihenfolge bestimmt die Anzeige.
SCHICHTEN = ["Frühdienst", "Spätdienst", "Nachtdienst"]

# Terminarten mit Symbol. "Visite" ist die ärztliche Visite im Haus.
TERMINARTEN = {
    "Visite": "🩺",
    "Arzttermin": "🏥",
    "Therapie": "🧑‍⚕️",
    "Friseur": "💇",
    "Fußpflege": "🦶",
    "Angehörige": "👪",
    "Betreuung": "🤝",
    "Sonstiges": "📌",
}

WOCHENTAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag",
              "Freitag", "Samstag", "Sonntag"]

MONATSNAMEN = ["Januar", "Februar", "März", "April", "Mai", "Juni",
               "Juli", "August", "September", "Oktober", "November", "Dezember"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS benutzer (
    id            INTEGER PRIMARY KEY,
    benutzername  TEXT NOT NULL UNIQUE,
    anzeigename   TEXT NOT NULL,
    passwort_hash TEXT NOT NULL,
    rolle         TEXT NOT NULL DEFAULT 'pflege',  -- 'pflege' oder 'leitung'
    passwort_neu  INTEGER NOT NULL DEFAULT 1,      -- 1 = muss Passwort ändern
    aktiv         INTEGER NOT NULL DEFAULT 1,
    erstellt_am   TEXT NOT NULL DEFAULT (date('now'))
);

-- Bewohnerinnen und Bewohner der Einrichtung.
CREATE TABLE IF NOT EXISTS bewohner (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    zimmer      TEXT NOT NULL DEFAULT '',
    wohnbereich TEXT NOT NULL DEFAULT '',
    hinweis     TEXT NOT NULL DEFAULT '',
    aktiv       INTEGER NOT NULL DEFAULT 1,
    erstellt_am TEXT NOT NULL DEFAULT (date('now'))
);

-- Ärztinnen und Ärzte sowie Therapeuten – Grundlage für das Visiten-Menü.
CREATE TABLE IF NOT EXISTS aerzte (
    id            INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    fachrichtung  TEXT NOT NULL DEFAULT '',
    telefon       TEXT NOT NULL DEFAULT '',
    visitentag    TEXT NOT NULL DEFAULT '',  -- z. B. "Dienstag" (fester Visitentag)
    hinweis       TEXT NOT NULL DEFAULT '',
    aktiv         INTEGER NOT NULL DEFAULT 1,
    erstellt_am   TEXT NOT NULL DEFAULT (date('now'))
);

-- Termine im Kalender.
CREATE TABLE IF NOT EXISTS termine (
    id           INTEGER PRIMARY KEY,
    datum        TEXT NOT NULL,               -- ISO: 2027-01-01
    uhrzeit      TEXT NOT NULL DEFAULT '',    -- "10:00", leer = ganztägig
    art          TEXT NOT NULL DEFAULT 'Sonstiges',
    bewohner_id  INTEGER REFERENCES bewohner(id),
    arzt_id      INTEGER REFERENCES aerzte(id),
    titel        TEXT NOT NULL DEFAULT '',
    notiz        TEXT NOT NULL DEFAULT '',
    erledigt     INTEGER NOT NULL DEFAULT 0,
    angelegt_von INTEGER REFERENCES benutzer(id),
    erstellt_am  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_termine_datum ON termine(datum);

-- Schichtübergaben.
CREATE TABLE IF NOT EXISTS uebergaben (
    id           INTEGER PRIMARY KEY,
    datum        TEXT NOT NULL,
    schicht      TEXT NOT NULL,
    bewohner_id  INTEGER REFERENCES bewohner(id),  -- optional: betrifft eine Person
    text         TEXT NOT NULL,
    wichtig      INTEGER NOT NULL DEFAULT 0,
    verfasser_id INTEGER NOT NULL REFERENCES benutzer(id),
    erstellt_am  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_uebergaben_datum ON uebergaben(datum);

-- Fehlgeschlagene Anmeldungen (Schutz vor Passwort-Raten).
CREATE TABLE IF NOT EXISTS login_versuche (
    id           INTEGER PRIMARY KEY,
    benutzername TEXT NOT NULL,
    ip           TEXT NOT NULL,
    zeit         TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_login_versuche_zeit ON login_versuche(zeit);
"""

# Erstzugang. Das Passwort muss bei der ersten Anmeldung geändert werden.
STANDARD_BENUTZER = [("leitung", "Leitung", "start-2026", "leitung")]


def verbinden() -> sqlite3.Connection:
    conn = sqlite3.connect(DATENBANK)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = verbinden()
    try:
        conn.executescript(SCHEMA)
        if conn.execute("SELECT COUNT(*) AS n FROM benutzer").fetchone()["n"] == 0:
            for benutzername, anzeigename, passwort, rolle in STANDARD_BENUTZER:
                conn.execute(
                    "INSERT INTO benutzer (benutzername, anzeigename, passwort_hash, rolle)"
                    " VALUES (?, ?, ?, ?)",
                    (benutzername, anzeigename, generate_password_hash(passwort), rolle),
                )
        conn.commit()
    finally:
        conn.close()


def datum_de(iso: str) -> str:
    """2027-01-01 -> 01.01.2027"""
    jahr, monat, tag = iso[:10].split("-")
    return f"{tag}.{monat}.{jahr}"


def wochentag(iso: str) -> str:
    """2027-01-01 -> Freitag"""
    return WOCHENTAGE[datetime.date.fromisoformat(iso[:10]).weekday()]


def montag_der_woche(tag: datetime.date) -> datetime.date:
    return tag - datetime.timedelta(days=tag.weekday())


if __name__ == "__main__":
    init_db()
    print(f"Datenbank bereit: {DATENBANK}")
