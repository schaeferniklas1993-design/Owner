#!/usr/bin/env python3
"""Kommandozeile des Haushaltsbuchs – wird von den Finanz-Agents benutzt.

Beispiele:
  python3 cli.py --benutzer niklas einnahme 2450,00 --kategorie Gehalt --beschreibung "Gehalt Juli"
  python3 cli.py --benutzer partnerin ausgabe 54,30 --kategorie Lebensmittel --datum 2026-07-05
  python3 cli.py --benutzer niklas uebersicht --monat 2026-07
  python3 cli.py bericht --monat 2026-07
  python3 cli.py kategorien
  python3 cli.py dauerauftraege
  python3 cli.py gehalt niklas 2450,00
  python3 cli.py passwort niklas
"""
import argparse
import datetime
import getpass
import sys

from werkzeug.security import generate_password_hash

import database
from database import cent, euro


def _benutzer(conn, benutzername: str):
    zeile = conn.execute(
        "SELECT * FROM benutzer WHERE benutzername = ?", (benutzername,)
    ).fetchone()
    if not zeile:
        namen = [r["benutzername"] for r in conn.execute("SELECT benutzername FROM benutzer")]
        sys.exit(f"Unbekannter Benutzer '{benutzername}'. Vorhanden: {', '.join(namen)}")
    return zeile


def _kategorie(conn, name: str, art: str):
    zeile = conn.execute(
        "SELECT * FROM kategorien WHERE lower(name) = lower(?) AND art = ?", (name, art)
    ).fetchone()
    if not zeile:
        namen = [r["name"] for r in conn.execute(
            "SELECT name FROM kategorien WHERE art = ? ORDER BY name", (art,))]
        sys.exit(f"Unbekannte {art.capitalize()}-Kategorie '{name}'. Vorhanden: {', '.join(namen)}")
    return zeile


def buchen(conn, args, art: str) -> None:
    if not args.benutzer:
        sys.exit("Bitte --benutzer angeben (niklas oder partnerin).")
    benutzer = _benutzer(conn, args.benutzer)
    kategorie = _kategorie(conn, args.kategorie, art)
    datum = args.datum or datetime.date.today().isoformat()
    datetime.date.fromisoformat(datum)
    betrag = cent(args.betrag)
    conn.execute(
        "INSERT INTO buchungen (benutzer_id, art, kategorie_id, betrag_cent, beschreibung, datum)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (benutzer["id"], art, kategorie["id"], betrag, args.beschreibung or "", datum),
    )
    conn.commit()
    vorzeichen = "+" if art == "einnahme" else "-"
    print(f"Gebucht für {benutzer['anzeigename']}: {vorzeichen}{euro(betrag)}"
          f" · {kategorie['name']} · {datum}"
          + (f" · {args.beschreibung}" if args.beschreibung else ""))


def _monat(args) -> str:
    if args.monat:
        datetime.datetime.strptime(args.monat, "%Y-%m")
        return args.monat
    return datetime.date.today().strftime("%Y-%m")


def uebersicht(conn, args) -> None:
    monat = _monat(args)
    if not args.benutzer:
        sys.exit("Bitte --benutzer angeben (für den Haushalt: 'bericht' verwenden).")
    benutzer = _benutzer(conn, args.benutzer)
    print(f"Übersicht {benutzer['anzeigename']} – {monat}")
    summen = {"einnahme": 0, "ausgabe": 0}
    for zeile in conn.execute(
        """SELECT b.art, b.datum, b.betrag_cent, b.beschreibung, k.name AS kategorie
           FROM buchungen b JOIN kategorien k ON k.id = b.kategorie_id
           WHERE b.benutzer_id = ? AND strftime('%Y-%m', b.datum) = ?
           ORDER BY b.datum, b.id""",
        (benutzer["id"], monat),
    ):
        summen[zeile["art"]] += zeile["betrag_cent"]
        vorzeichen = "+" if zeile["art"] == "einnahme" else "-"
        print(f"  {zeile['datum']}  {vorzeichen}{euro(zeile['betrag_cent']):>14}"
              f"  {zeile['kategorie']:<20} {zeile['beschreibung']}")
    print(f"  Einnahmen: {euro(summen['einnahme'])}   Ausgaben: {euro(summen['ausgabe'])}"
          f"   Saldo: {euro(summen['einnahme'] - summen['ausgabe'])}")


def bericht(conn, args) -> None:
    monat = _monat(args)
    print(f"Haushaltsbericht – {monat}")
    gesamt = {"einnahme": 0, "ausgabe": 0}
    for benutzer in conn.execute("SELECT * FROM benutzer ORDER BY id"):
        summen = {"einnahme": 0, "ausgabe": 0}
        for zeile in conn.execute(
            "SELECT art, SUM(betrag_cent) AS s FROM buchungen"
            " WHERE benutzer_id = ? AND strftime('%Y-%m', datum) = ? GROUP BY art",
            (benutzer["id"], monat),
        ):
            summen[zeile["art"]] = zeile["s"]
            gesamt[zeile["art"]] += zeile["s"]
        print(f"  {benutzer['anzeigename']:<12} Einnahmen {euro(summen['einnahme']):>14}"
              f"   Ausgaben {euro(summen['ausgabe']):>14}"
              f"   Saldo {euro(summen['einnahme'] - summen['ausgabe']):>14}")
    print(f"  {'Haushalt':<12} Einnahmen {euro(gesamt['einnahme']):>14}"
          f"   Ausgaben {euro(gesamt['ausgabe']):>14}"
          f"   Saldo {euro(gesamt['einnahme'] - gesamt['ausgabe']):>14}")
    print("\n  Ausgaben nach Kategorie:")
    for zeile in conn.execute(
        """SELECT k.name, SUM(b.betrag_cent) AS s FROM buchungen b
           JOIN kategorien k ON k.id = b.kategorie_id
           WHERE b.art = 'ausgabe' AND strftime('%Y-%m', b.datum) = ?
           GROUP BY k.id ORDER BY s DESC""",
        (monat,),
    ):
        print(f"    {zeile['name']:<22} {euro(zeile['s']):>14}")


def kategorien(conn, args) -> None:
    for art in ("einnahme", "ausgabe"):
        print(f"{art.capitalize()}-Kategorien:")
        for zeile in conn.execute(
            "SELECT name FROM kategorien WHERE art = ? ORDER BY name", (art,)
        ):
            print(f"  - {zeile['name']}")


def dauerauftraege(conn, args) -> None:
    for zeile in conn.execute(
        """SELECT d.*, k.name AS kategorie, u.anzeigename AS person
           FROM dauerauftraege d
           JOIN kategorien k ON k.id = d.kategorie_id
           JOIN benutzer u ON u.id = d.benutzer_id ORDER BY d.monatstag"""
    ):
        status = "aktiv" if zeile["aktiv"] and zeile["betrag_cent"] > 0 else "inaktiv"
        print(f"  [{zeile['id']}] {zeile['person']:<12} Tag {zeile['monatstag']:>2}"
              f"  {euro(zeile['betrag_cent']):>14}  {zeile['kategorie']:<12}"
              f"  {zeile['beschreibung']:<24} ({status})")


def gehalt(conn, args) -> None:
    benutzer = _benutzer(conn, args.benutzername)
    betrag = cent(args.betrag)
    zeile = conn.execute(
        """SELECT d.id FROM dauerauftraege d JOIN kategorien k ON k.id = d.kategorie_id
           WHERE d.benutzer_id = ? AND k.name = 'Gehalt' ORDER BY d.id LIMIT 1""",
        (benutzer["id"],),
    ).fetchone()
    if not zeile:
        sys.exit("Kein Gehalts-Dauerauftrag gefunden.")
    conn.execute(
        "UPDATE dauerauftraege SET betrag_cent = ?, aktiv = 1 WHERE id = ?",
        (betrag, zeile["id"]),
    )
    neu = database.dauerauftraege_ausfuehren(conn)
    conn.commit()
    print(f"Gehalt von {benutzer['anzeigename']} auf {euro(betrag)} gesetzt"
          f" (Zahltag: {benutzer['gehaltstag']}.). Nachgebuchte Monate: {neu}.")


def sicherung(conn, args) -> None:
    import os
    import sqlite3
    ordner = os.path.join(database.BASIS_VERZEICHNIS, "sicherungen")
    os.makedirs(ordner, exist_ok=True)
    ziel = os.path.join(ordner, f"haushalt-{datetime.date.today().isoformat()}.db")
    ziel_conn = sqlite3.connect(ziel)
    with ziel_conn:
        conn.backup(ziel_conn)
    ziel_conn.close()
    print(f"Sicherung erstellt: {ziel}")


def passwort(conn, args) -> None:
    benutzer = _benutzer(conn, args.benutzername)
    neu = getpass.getpass(f"Neues Passwort für {benutzer['anzeigename']}: ")
    if len(neu) < 8:
        sys.exit("Das Passwort muss mindestens 8 Zeichen haben.")
    if neu != getpass.getpass("Passwort wiederholen: "):
        sys.exit("Die Passwörter stimmen nicht überein.")
    conn.execute(
        "UPDATE benutzer SET passwort_hash = ? WHERE id = ?",
        (generate_password_hash(neu), benutzer["id"]),
    )
    conn.commit()
    print("Passwort geändert.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Haushaltsbuch-Kommandozeile")
    parser.add_argument("--benutzer", help="Benutzername (niklas oder partnerin)")
    sub = parser.add_subparsers(dest="befehl", required=True)

    for art, hilfe in (("einnahme", "Einnahme buchen"), ("ausgabe", "Ausgabe buchen")):
        p = sub.add_parser(art, help=hilfe)
        p.add_argument("betrag", help="Betrag in Euro, z. B. 54,30")
        p.add_argument("--kategorie", required=True)
        p.add_argument("--datum", help="JJJJ-MM-TT (Standard: heute)")
        p.add_argument("--beschreibung", default="")

    p = sub.add_parser("uebersicht", help="Monatsübersicht eines Benutzers")
    p.add_argument("--monat", help="JJJJ-MM (Standard: aktueller Monat)")

    p = sub.add_parser("bericht", help="Haushaltsbericht für beide Personen")
    p.add_argument("--monat", help="JJJJ-MM (Standard: aktueller Monat)")

    sub.add_parser("kategorien", help="Alle Kategorien anzeigen")
    sub.add_parser("dauerauftraege", help="Daueraufträge anzeigen")

    p = sub.add_parser("gehalt", help="Monatliches Gehalt als Dauerauftrag setzen")
    p.add_argument("benutzername")
    p.add_argument("betrag", help="Netto-Gehalt in Euro, z. B. 2450,00")

    p = sub.add_parser("passwort", help="Passwort eines Benutzers ändern")
    p.add_argument("benutzername")

    sub.add_parser("sicherung", help="Sicherungskopie der Datenbank erstellen")

    args = parser.parse_args()
    database.init_db()
    conn = database.verbinden()
    try:
        database.dauerauftraege_ausfuehren(conn)
        {
            "einnahme": lambda: buchen(conn, args, "einnahme"),
            "ausgabe": lambda: buchen(conn, args, "ausgabe"),
            "uebersicht": lambda: uebersicht(conn, args),
            "bericht": lambda: bericht(conn, args),
            "kategorien": lambda: kategorien(conn, args),
            "dauerauftraege": lambda: dauerauftraege(conn, args),
            "gehalt": lambda: gehalt(conn, args),
            "passwort": lambda: passwort(conn, args),
            "sicherung": lambda: sicherung(conn, args),
        }[args.befehl]()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
