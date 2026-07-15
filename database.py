"""Datenbank-Schicht des Haushaltsbuchs.

SQLite-Datei: haushalt.db (überschreibbar via Umgebungsvariable BUDGET_DB).
Beträge werden als Cent (Integer) gespeichert, um Rundungsfehler zu vermeiden.
"""
import datetime
import os
import sqlite3

from werkzeug.security import generate_password_hash

BASIS_VERZEICHNIS = os.path.dirname(os.path.abspath(__file__))
DB_PFAD = os.environ.get("BUDGET_DB", os.path.join(BASIS_VERZEICHNIS, "haushalt.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS benutzer (
    id                    INTEGER PRIMARY KEY,
    benutzername          TEXT UNIQUE NOT NULL,
    anzeigename           TEXT NOT NULL,
    passwort_hash         TEXT NOT NULL,
    gehaltstag            INTEGER NOT NULL DEFAULT 1,
    muss_passwort_aendern INTEGER NOT NULL DEFAULT 1,
    startsaldo_cent       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS kategorien (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    art  TEXT NOT NULL CHECK (art IN ('einnahme', 'ausgabe')),
    UNIQUE (name, art)
);

CREATE TABLE IF NOT EXISTS dauerauftraege (
    id           INTEGER PRIMARY KEY,
    benutzer_id  INTEGER NOT NULL REFERENCES benutzer(id),
    art          TEXT NOT NULL CHECK (art IN ('einnahme', 'ausgabe')),
    kategorie_id INTEGER NOT NULL REFERENCES kategorien(id),
    betrag_cent  INTEGER NOT NULL DEFAULT 0,
    beschreibung TEXT NOT NULL,
    monatstag    INTEGER NOT NULL CHECK (monatstag BETWEEN 1 AND 28),
    aktiv        INTEGER NOT NULL DEFAULT 1,
    erstellt_am  TEXT NOT NULL DEFAULT (date('now'))
);

CREATE TABLE IF NOT EXISTS buchungen (
    id              INTEGER PRIMARY KEY,
    benutzer_id     INTEGER NOT NULL REFERENCES benutzer(id),
    art             TEXT NOT NULL CHECK (art IN ('einnahme', 'ausgabe')),
    kategorie_id    INTEGER NOT NULL REFERENCES kategorien(id),
    betrag_cent     INTEGER NOT NULL CHECK (betrag_cent > 0),
    beschreibung    TEXT NOT NULL DEFAULT '',
    datum           TEXT NOT NULL,
    dauerauftrag_id INTEGER REFERENCES dauerauftraege(id),
    erstellt_am     TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_buchungen_datum ON buchungen(datum);
CREATE INDEX IF NOT EXISTS idx_buchungen_benutzer ON buchungen(benutzer_id);

-- Fehlgeschlagene Anmeldungen für die Login-Bremse (Schutz vor Passwort-Raten).
CREATE TABLE IF NOT EXISTS login_versuche (
    id           INTEGER PRIMARY KEY,
    benutzername TEXT NOT NULL,
    ip           TEXT NOT NULL,
    zeit         TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_login_versuche_zeit ON login_versuche(zeit);

-- Pro Dauerauftrag und Monat höchstens eine Buchung, auch wenn mehrere
-- Server-Prozesse gleichzeitig nachbuchen.
CREATE UNIQUE INDEX IF NOT EXISTS idx_dauerauftrag_monat
    ON buchungen(dauerauftrag_id, strftime('%Y-%m', datum))
    WHERE dauerauftrag_id IS NOT NULL;

-- Gemeinsame Sparziele (Sparkonto), z. B. Urlaub oder Hauskauf.
CREATE TABLE IF NOT EXISTS sparziele (
    id             INTEGER PRIMARY KEY,
    name           TEXT NOT NULL,
    icon           TEXT NOT NULL DEFAULT '🎯',
    zielbetrag_cent INTEGER NOT NULL DEFAULT 0,   -- 0 = kein festes Ziel
    aktiv          INTEGER NOT NULL DEFAULT 1,
    erstellt_am    TEXT NOT NULL DEFAULT (date('now'))
);

-- Ein- und Auszahlungen auf ein Sparziel (positiv = Einzahlung, negativ = Entnahme).
CREATE TABLE IF NOT EXISTS spar_bewegungen (
    id           INTEGER PRIMARY KEY,
    sparziel_id  INTEGER NOT NULL REFERENCES sparziele(id),
    benutzer_id  INTEGER NOT NULL REFERENCES benutzer(id),
    betrag_cent  INTEGER NOT NULL,
    beschreibung TEXT NOT NULL DEFAULT '',
    datum        TEXT NOT NULL,
    erstellt_am  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_spar_bewegungen_ziel ON spar_bewegungen(sparziel_id);
"""

# Die beiden Zugänge des Haushalts. Die Startpasswörter gelten nur für den
# ersten Login – die App fragt dann sofort nach einem eigenen Passwort.
STANDARD_BENUTZER = [
    # (benutzername, anzeigename, startpasswort, gehaltstag)
    ("niklas", "Niklas", "niklas-start", 15),   # Gehalt Mitte des Monats
    ("maeuschen", "Mäuschen", "maeuschen-start", 1),  # Gehalt am Monatsersten
]

STANDARD_KATEGORIEN = {
    "einnahme": [
        "Gehalt", "Nebeneinkünfte", "Bonus & Prämie", "Verkauf",
        "Zinsen & Kapitalerträge", "Kindergeld", "Rückerstattung",
        "Geschenk", "Sonstige Einnahme",
    ],
    "ausgabe": [
        "Miete", "Nebenkosten", "Handy & Internet", "Lebensmittel",
        "Versicherungen", "Kredite & Raten", "Mobilität", "Gesundheit",
        "Kleidung", "Freizeit", "Restaurant & Café", "Abos & Medien",
        "Haushalt", "Möbel & Technik", "Urlaub & Reisen", "Kinder",
        "Haustiere", "Geschenke", "Bildung", "Spenden",
        "Steuern & Gebühren", "Sparen & Rücklagen", "Sonstige Ausgabe",
    ],
}


def verbinden() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PFAD)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Legt Schema und Grunddaten an; mehrfacher Aufruf ist unschädlich."""
    conn = verbinden()
    try:
        conn.executescript(SCHEMA)

        # Migration für Datenbanken aus früheren Versionen: Beim ersten Login
        # wählt jeder Benutzer ein eigenes Passwort direkt in der Web-Oberfläche.
        spalten = [z["name"] for z in conn.execute("PRAGMA table_info(benutzer)")]
        if "muss_passwort_aendern" not in spalten:
            conn.execute(
                "ALTER TABLE benutzer ADD COLUMN"
                " muss_passwort_aendern INTEGER NOT NULL DEFAULT 1"
            )
        if "startsaldo_cent" not in spalten:
            conn.execute(
                "ALTER TABLE benutzer ADD COLUMN startsaldo_cent INTEGER NOT NULL DEFAULT 0"
            )

        # Migration: Aus „Partnerin" wurde „Mäuschen" – Bestandsdaten umbenennen.
        conn.execute(
            "UPDATE benutzer SET benutzername = 'maeuschen', anzeigename = 'Mäuschen'"
            " WHERE benutzername = 'partnerin'"
        )
        conn.execute(
            "UPDATE dauerauftraege SET beschreibung = 'Gehalt Mäuschen'"
            " WHERE beschreibung = 'Gehalt Partnerin'"
        )
        conn.execute(
            "UPDATE buchungen SET beschreibung = 'Gehalt Mäuschen'"
            " WHERE beschreibung = 'Gehalt Partnerin'"
        )

        if conn.execute("SELECT COUNT(*) AS n FROM benutzer").fetchone()["n"] == 0:
            for benutzername, anzeigename, passwort, gehaltstag in STANDARD_BENUTZER:
                conn.execute(
                    "INSERT INTO benutzer (benutzername, anzeigename, passwort_hash, gehaltstag)"
                    " VALUES (?, ?, ?, ?)",
                    (benutzername, anzeigename, generate_password_hash(passwort), gehaltstag),
                )

        # Standardkategorien anlegen bzw. neue nachrüsten (bestehende bleiben unberührt).
        for art, namen in STANDARD_KATEGORIEN.items():
            for name in namen:
                conn.execute(
                    "INSERT OR IGNORE INTO kategorien (name, art) VALUES (?, ?)", (name, art)
                )

        if conn.execute("SELECT COUNT(*) AS n FROM dauerauftraege").fetchone()["n"] == 0:
            gehalt = conn.execute(
                "SELECT id FROM kategorien WHERE name = 'Gehalt' AND art = 'einnahme'"
            ).fetchone()["id"]
            for zeile in conn.execute("SELECT id, anzeigename, gehaltstag FROM benutzer"):
                # Betrag 0 = inaktiv, bis der echte Gehaltsbetrag gesetzt wird.
                conn.execute(
                    "INSERT INTO dauerauftraege (benutzer_id, art, kategorie_id, betrag_cent,"
                    " beschreibung, monatstag, aktiv) VALUES (?, 'einnahme', ?, 0, ?, ?, 0)",
                    (zeile["id"], gehalt, f"Gehalt {zeile['anzeigename']}", zeile["gehaltstag"]),
                )

        # Ein paar Sparziele als Startvorlage (nur beim allerersten Anlegen).
        if conn.execute("SELECT COUNT(*) AS n FROM sparziele").fetchone()["n"] == 0:
            for name, icon, ziel in [
                ("Urlaub", "🏖️", 0),
                ("Eigenes Haus", "🏡", 0),
                ("Notgroschen", "🛟", 0),
            ]:
                conn.execute(
                    "INSERT INTO sparziele (name, icon, zielbetrag_cent) VALUES (?, ?, ?)",
                    (name, icon, ziel),
                )

        conn.commit()
    finally:
        conn.close()


def dauerauftraege_ausfuehren(conn: sqlite3.Connection, heute: datetime.date | None = None) -> int:
    """Bucht fällige Daueraufträge (z. B. Gehälter) der letzten 12 Monate nach.

    Idempotent: pro Dauerauftrag und Monat entsteht höchstens eine Buchung.
    Gibt die Anzahl neu erzeugter Buchungen zurück.
    """
    heute = heute or datetime.date.today()
    neu = 0
    for da in conn.execute(
        "SELECT * FROM dauerauftraege WHERE aktiv = 1 AND betrag_cent > 0"
    ).fetchall():
        erstellt = datetime.date.fromisoformat(da["erstellt_am"][:10])
        jahr, monat = heute.year, heute.month
        for _ in range(12):
            faellig = datetime.date(jahr, monat, da["monatstag"])
            if faellig <= heute and faellig >= erstellt.replace(day=1):
                vorhanden = conn.execute(
                    "SELECT 1 FROM buchungen WHERE dauerauftrag_id = ?"
                    " AND strftime('%Y-%m', datum) = ?",
                    (da["id"], faellig.strftime("%Y-%m")),
                ).fetchone()
                if not vorhanden:
                    cursor = conn.execute(
                        "INSERT OR IGNORE INTO buchungen (benutzer_id, art, kategorie_id,"
                        " betrag_cent, beschreibung, datum, dauerauftrag_id)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (da["benutzer_id"], da["art"], da["kategorie_id"], da["betrag_cent"],
                         da["beschreibung"], faellig.isoformat(), da["id"]),
                    )
                    neu += cursor.rowcount
            monat -= 1
            if monat == 0:
                jahr, monat = jahr - 1, 12
    if neu:
        conn.commit()
    return neu


def euro(betrag_cent: int) -> str:
    """Formatiert Cent als deutschen Euro-Betrag, z. B. 123456 -> '1.234,56 €'."""
    vorzeichen = "-" if betrag_cent < 0 else ""
    betrag_cent = abs(betrag_cent)
    ganz, rest = divmod(betrag_cent, 100)
    return f"{vorzeichen}{ganz:,}".replace(",", ".") + f",{rest:02d} €"


def cent(betrag: str) -> int:
    """Wandelt Eingaben wie '1.234,56', '1234.56' oder '1234' in Cent um."""
    wert = cent_signed(betrag)
    if wert <= 0:
        raise ValueError("Der Betrag muss größer als 0 sein.")
    return wert


def cent_signed(betrag: str) -> int:
    """Wie cent(), erlaubt aber auch 0 und negative Werte (z. B. Kontostand).

    Versteht deutsche und englische Schreibweisen:
      '1.234,56' -> 123456   '1234.56' -> 123456   '5.000' -> 500000
      '1234'     -> 123400    '-120,50' -> -12050
    """
    text = str(betrag).strip().replace("€", "").replace(" ", "")
    if "," in text:
        # Deutsch: Punkt ist Tausender-Trenner, Komma das Dezimalzeichen.
        text = text.replace(".", "").replace(",", ".")
    elif text.count(".") > 1:
        # Mehrere Punkte -> alle sind Tausender-Trenner (z. B. 1.234.567).
        text = text.replace(".", "")
    elif "." in text:
        # Ein Punkt ohne Komma: 3 Nachkommastellen = Tausender (5.000),
        # sonst Dezimalpunkt (1234.56).
        if len(text.rsplit(".", 1)[1]) == 3:
            text = text.replace(".", "")
    return round(float(text) * 100)


if __name__ == "__main__":
    init_db()
    print(f"Datenbank bereit: {DB_PFAD}")
