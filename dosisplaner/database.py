"""Datenbank des Dosisplaners.

Alles liegt in einer einzigen SQLite-Datei neben diesem Skript.
Anlegen/aktualisieren:  python3 database.py
"""
import datetime
import os
import sqlite3

from werkzeug.security import generate_password_hash

BASIS_VERZEICHNIS = os.path.dirname(os.path.abspath(__file__))
DATENBANK = os.path.join(BASIS_VERZEICHNIS, "dosisplaner.db")

# Wie es dir ging – für den Rückblick und das Arztgespräch.
BEFINDEN = {
    5: ("Sehr gut", "😊"),
    4: ("Gut", "🙂"),
    3: ("Geht so", "😐"),
    2: ("Schwer", "😕"),
    1: ("Sehr schwer", "😣"),
}

# Häufige Begleiterscheinungen beim Reduzieren. Keine Diagnose – nur eine
# Gedächtnisstütze, damit du beim Termin nichts vergisst.
SYMPTOME = [
    "Schlafprobleme", "Unruhe", "Angst", "Reizbarkeit", "Schwitzen",
    "Übelkeit", "Kopfschmerzen", "Schmerzen", "Benommenheit", "Niedergeschlagenheit",
]

# Substitutionsmittel. Dosis und Vergabe legt die Substitutionsärztin bzw.
# der Substitutionsarzt fest – hier wird nur festgehalten, was verordnet
# wurde und was tatsächlich war.
SUBSTITUTE = {
    "polamidon": ("Polamidon", "Levomethadon"),
    "substitol": ("Substitol", "Morphinsulfat retard"),
}

# Wie die Dosis an dem Tag kam.
VERGABE = ["Sichtvergabe", "Take-home", "Ausgelassen"]

# Was bei einem Rückfall eingetragen werden kann.
SUBSTANZEN = [
    "Kokain", "Crack", "Alkohol", "Benzodiazepine", "Cannabis",
    "Amphetamin", "Heroin", "Anderes",
]

# Auslöser – der eigentlich wertvolle Teil. Muster erkennt man erst,
# wenn mehrere Einträge beieinanderstehen.
AUSLOESER = [
    "Stress", "Streit", "Einsamkeit", "Langeweile", "Geld da",
    "Alte Kontakte", "Feiern", "Schlaflos", "Craving ohne Anlass",
    "Schmerzen", "Frust", "Gute Laune",
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS benutzer (
    id            INTEGER PRIMARY KEY,
    benutzername  TEXT NOT NULL UNIQUE,
    anzeigename   TEXT NOT NULL,
    passwort_hash TEXT NOT NULL,
    passwort_neu  INTEGER NOT NULL DEFAULT 1,
    erstellt_am   TEXT NOT NULL DEFAULT (date('now'))
);

-- Der Soll-Plan: Abschnitte mit jeweils einer Tagesdosis.
-- Die Werte trägst du selbst ein – abgestimmt mit deiner Ärztin/deinem Arzt.
CREATE TABLE IF NOT EXISTS plan_phasen (
    id          INTEGER PRIMARY KEY,
    von         TEXT NOT NULL,            -- ISO-Datum, Beginn des Abschnitts
    bis         TEXT NOT NULL,            -- ISO-Datum, Ende (einschließlich)
    soll_mg     REAL NOT NULL,            -- Tagesdosis in mg für diesen Abschnitt
    notiz       TEXT NOT NULL DEFAULT '',
    erstellt_am TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_phasen_von ON plan_phasen(von);

-- Was du tatsächlich genommen hast – ein Eintrag pro Tag.
CREATE TABLE IF NOT EXISTS eintraege (
    id          INTEGER PRIMARY KEY,
    datum       TEXT NOT NULL UNIQUE,     -- ein Eintrag je Tag
    ist_mg      REAL NOT NULL,
    befinden    INTEGER,                  -- 1 bis 5, siehe BEFINDEN
    symptome    TEXT NOT NULL DEFAULT '', -- kommagetrennt
    notiz       TEXT NOT NULL DEFAULT '',
    erstellt_am TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_eintraege_datum ON eintraege(datum);

-- Substitution: was verordnet ist (Polamidon, Substitol).
-- Festgelegt wird das in der Praxis – hier steht nur, was dort vereinbart
-- wurde, damit du es nachlesen und daneben halten kannst.
CREATE TABLE IF NOT EXISTS subst_plan (
    id          INTEGER PRIMARY KEY,
    mittel      TEXT NOT NULL,            -- Schlüssel aus SUBSTITUTE
    von         TEXT NOT NULL,
    bis         TEXT NOT NULL,            -- einschließlich
    soll_mg     REAL NOT NULL,
    notiz       TEXT NOT NULL DEFAULT '',
    erstellt_am TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_subst_plan ON subst_plan(mittel, von);

-- Substitution: was an dem Tag tatsächlich war.
CREATE TABLE IF NOT EXISTS subst_eintraege (
    id          INTEGER PRIMARY KEY,
    datum       TEXT NOT NULL,
    mittel      TEXT NOT NULL,
    ist_mg      REAL NOT NULL,
    vergabe     TEXT NOT NULL DEFAULT '', -- Sichtvergabe / Take-home / Ausgelassen
    notiz       TEXT NOT NULL DEFAULT '',
    erstellt_am TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    UNIQUE (datum, mittel)
);
CREATE INDEX IF NOT EXISTS idx_subst_eintraege ON subst_eintraege(mittel, datum);

-- Rückfälle: offen festhalten, was war – ohne Bewertung.
-- Der Sinn ist nicht die Zahl, sondern das Muster dahinter.
CREATE TABLE IF NOT EXISTS konsum (
    id          INTEGER PRIMARY KEY,
    datum       TEXT NOT NULL,
    uhrzeit     TEXT NOT NULL DEFAULT '',
    substanz    TEXT NOT NULL,
    menge       TEXT NOT NULL DEFAULT '', -- frei, oft nicht bezifferbar
    ausloeser   TEXT NOT NULL DEFAULT '', -- kommagetrennt, siehe AUSLOESER
    davor       INTEGER,                  -- Befinden 1–5 vorher
    danach      INTEGER,                  -- Befinden 1–5 danach
    besprochen  TEXT NOT NULL DEFAULT '', -- ja / noch nicht / nein
    notiz       TEXT NOT NULL DEFAULT '',
    erstellt_am TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_konsum_datum ON konsum(datum);

-- Eigene Erfolge und Erinnerungen, die guttun.
CREATE TABLE IF NOT EXISTS erfolge (
    id          INTEGER PRIMARY KEY,
    datum       TEXT NOT NULL,
    text        TEXT NOT NULL,
    erstellt_am TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS login_versuche (
    id   INTEGER PRIMARY KEY,
    ip   TEXT NOT NULL,
    zeit TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

STANDARD_BENUTZER = [("ich", "Niklas", "start-2026")]


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
            for benutzername, anzeigename, passwort in STANDARD_BENUTZER:
                conn.execute(
                    "INSERT INTO benutzer (benutzername, anzeigename, passwort_hash)"
                    " VALUES (?, ?, ?)",
                    (benutzername, anzeigename, generate_password_hash(passwort)),
                )
        conn.commit()
    finally:
        conn.close()


def datum_de(iso: str) -> str:
    """2026-10-28 -> 28.10.2026"""
    jahr, monat, tag = iso[:10].split("-")
    return f"{tag}.{monat}.{jahr}"


def soll_fuer(conn: sqlite3.Connection, datum: str) -> float | None:
    """Soll-Dosis für einen Tag laut Plan; None, wenn kein Abschnitt passt."""
    zeile = conn.execute(
        "SELECT soll_mg FROM plan_phasen WHERE ? BETWEEN von AND bis"
        " ORDER BY von DESC LIMIT 1",
        (datum,),
    ).fetchone()
    return zeile["soll_mg"] if zeile else None


def soll_subst_fuer(conn: sqlite3.Connection, mittel: str, datum: str) -> float | None:
    """Verordnete Dosis eines Substitutionsmittels an einem Tag."""
    zeile = conn.execute(
        "SELECT soll_mg FROM subst_plan WHERE mittel = ? AND ? BETWEEN von AND bis"
        " ORDER BY von DESC LIMIT 1",
        (mittel, datum),
    ).fetchone()
    return zeile["soll_mg"] if zeile else None


def mg(wert: float | None) -> str:
    """500.0 -> '500 mg', 487.5 -> '487,5 mg'"""
    if wert is None:
        return "–"
    if float(wert).is_integer():
        return f"{int(wert)} mg"
    return f"{wert:.1f}".replace(".", ",") + " mg"


if __name__ == "__main__":
    init_db()
    print(f"Datenbank bereit: {DATENBANK}")
