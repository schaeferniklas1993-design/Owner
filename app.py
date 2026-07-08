"""Haushaltsbuch – Web-Oberfläche (Flask).

Start:  python3 app.py   →  http://localhost:5000
Zwei Zugänge: niklas / partnerin (Startpasswörter siehe README).
"""
import datetime
import functools
import os
import secrets

from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash

import database
from database import cent, euro

MONATSNAMEN = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
               "August", "September", "Oktober", "November", "Dezember"]


def _secret_key() -> str:
    pfad = os.path.join(database.BASIS_VERZEICHNIS, ".secret_key")
    if not os.path.exists(pfad):
        with open(pfad, "w") as f:
            f.write(secrets.token_hex(32))
        os.chmod(pfad, 0o600)
    with open(pfad) as f:
        return f.read().strip()


app = Flask(__name__)
database.init_db()
app.secret_key = _secret_key()
app.jinja_env.filters["euro"] = euro

# Auf einem öffentlichen Server (hinter HTTPS) mit BUDGET_HTTPS=1 starten:
# Session-Cookies werden dann nur noch verschlüsselt übertragen.
if os.environ.get("BUDGET_HTTPS") == "1":
    app.config.update(SESSION_COOKIE_SECURE=True, PREFERRED_URL_SCHEME="https")


@app.before_request
def vorbereiten():
    g.db = database.verbinden()
    database.dauerauftraege_ausfuehren(g.db)
    g.benutzer = None
    if session.get("benutzer_id"):
        g.benutzer = g.db.execute(
            "SELECT * FROM benutzer WHERE id = ?", (session["benutzer_id"],)
        ).fetchone()


@app.teardown_request
def aufraeumen(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def anmeldung_erforderlich(view):
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        if g.benutzer is None:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapper


@app.route("/login", methods=["GET", "POST"])
def login():
    fehler = None
    if request.method == "POST":
        zeile = g.db.execute(
            "SELECT * FROM benutzer WHERE benutzername = ?",
            (request.form.get("benutzername", "").strip().lower(),),
        ).fetchone()
        if zeile and check_password_hash(zeile["passwort_hash"], request.form.get("passwort", "")):
            session.clear()
            session["benutzer_id"] = zeile["id"]
            return redirect(url_for("dashboard"))
        fehler = "Benutzername oder Passwort ist falsch."
    return render_template("login.html", fehler=fehler)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


def _monat_aus_request() -> tuple[int, int]:
    heute = datetime.date.today()
    try:
        jahr, monat = map(int, request.args.get("monat", "").split("-"))
        datetime.date(jahr, monat, 1)
        return jahr, monat
    except (ValueError, AttributeError):
        return heute.year, heute.month


def _monat_verschieben(jahr: int, monat: int, schritt: int) -> str:
    index = jahr * 12 + (monat - 1) + schritt
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


@app.route("/")
@anmeldung_erforderlich
def dashboard():
    jahr, monat = _monat_aus_request()
    monat_key = f"{jahr:04d}-{monat:02d}"

    summen = {"einnahme": 0, "ausgabe": 0}
    pro_person = {}
    for zeile in g.db.execute(
        """SELECT b.art, b.benutzer_id, u.anzeigename, SUM(b.betrag_cent) AS summe
           FROM buchungen b JOIN benutzer u ON u.id = b.benutzer_id
           WHERE strftime('%Y-%m', b.datum) = ?
           GROUP BY b.art, b.benutzer_id""",
        (monat_key,),
    ):
        summen[zeile["art"]] += zeile["summe"]
        person = pro_person.setdefault(
            zeile["benutzer_id"], {"name": zeile["anzeigename"], "einnahme": 0, "ausgabe": 0}
        )
        person[zeile["art"]] = zeile["summe"]
    # Alle Benutzer anzeigen, auch ohne Buchungen im Monat.
    for u in g.db.execute("SELECT id, anzeigename FROM benutzer ORDER BY id"):
        pro_person.setdefault(u["id"], {"name": u["anzeigename"], "einnahme": 0, "ausgabe": 0})

    # Verlauf der letzten 6 Monate für das Balkendiagramm.
    verlauf = []
    for schritt in range(-5, 1):
        m_key = _monat_verschieben(jahr, monat, schritt)
        m_jahr, m_monat = map(int, m_key.split("-"))
        werte = {"einnahme": 0, "ausgabe": 0}
        for zeile in g.db.execute(
            "SELECT art, SUM(betrag_cent) AS summe FROM buchungen"
            " WHERE strftime('%Y-%m', datum) = ? GROUP BY art",
            (m_key,),
        ):
            werte[zeile["art"]] = zeile["summe"]
        verlauf.append({
            "label": f"{MONATSNAMEN[m_monat - 1][:3]} {str(m_jahr)[2:]}",
            "einnahme": werte["einnahme"] / 100,
            "ausgabe": werte["ausgabe"] / 100,
        })

    # Ausgaben nach Kategorie für das Ringdiagramm.
    kategorien_summen = [
        {"name": zeile["name"], "wert": zeile["summe"] / 100}
        for zeile in g.db.execute(
            """SELECT k.name, SUM(b.betrag_cent) AS summe
               FROM buchungen b JOIN kategorien k ON k.id = b.kategorie_id
               WHERE b.art = 'ausgabe' AND strftime('%Y-%m', b.datum) = ?
               GROUP BY k.id ORDER BY summe DESC""",
            (monat_key,),
        )
    ]

    letzte_buchungen = g.db.execute(
        """SELECT b.*, k.name AS kategorie, u.anzeigename AS person
           FROM buchungen b
           JOIN kategorien k ON k.id = b.kategorie_id
           JOIN benutzer u ON u.id = b.benutzer_id
           WHERE strftime('%Y-%m', b.datum) = ?
           ORDER BY b.datum DESC, b.id DESC LIMIT 8""",
        (monat_key,),
    ).fetchall()

    return render_template(
        "dashboard.html",
        monat_key=monat_key,
        monat_titel=f"{MONATSNAMEN[monat - 1]} {jahr}",
        vormonat=_monat_verschieben(jahr, monat, -1),
        naechster_monat=_monat_verschieben(jahr, monat, 1),
        einnahmen=summen["einnahme"],
        ausgaben=summen["ausgabe"],
        saldo=summen["einnahme"] - summen["ausgabe"],
        pro_person=list(pro_person.values()),
        verlauf=verlauf,
        kategorien_summen=kategorien_summen,
        letzte_buchungen=letzte_buchungen,
        kategorien=g.db.execute("SELECT * FROM kategorien ORDER BY art, name").fetchall(),
    )


@app.route("/buchungen", methods=["GET", "POST"])
@anmeldung_erforderlich
def buchungen():
    if request.method == "POST":
        try:
            betrag = cent(request.form["betrag"])
            art = request.form["art"]
            if art not in ("einnahme", "ausgabe"):
                raise ValueError("Ungültige Art.")
            kategorie = g.db.execute(
                "SELECT id FROM kategorien WHERE id = ? AND art = ?",
                (request.form["kategorie_id"], art),
            ).fetchone()
            if not kategorie:
                raise ValueError("Kategorie passt nicht zur gewählten Art.")
            datum = datetime.date.fromisoformat(request.form["datum"]).isoformat()
            g.db.execute(
                "INSERT INTO buchungen (benutzer_id, art, kategorie_id, betrag_cent,"
                " beschreibung, datum) VALUES (?, ?, ?, ?, ?, ?)",
                (g.benutzer["id"], art, kategorie["id"], betrag,
                 request.form.get("beschreibung", "").strip(), datum),
            )
            g.db.commit()
            flash("Buchung gespeichert.", "ok")
        except (ValueError, KeyError) as e:
            flash(f"Buchung nicht gespeichert: {e}", "fehler")
        return redirect(url_for("buchungen", monat=request.args.get("monat", "")))

    jahr, monat = _monat_aus_request()
    monat_key = f"{jahr:04d}-{monat:02d}"
    person_filter = request.args.get("person", "alle")

    sql = """SELECT b.*, k.name AS kategorie, u.anzeigename AS person, u.benutzername
             FROM buchungen b
             JOIN kategorien k ON k.id = b.kategorie_id
             JOIN benutzer u ON u.id = b.benutzer_id
             WHERE strftime('%Y-%m', b.datum) = ?"""
    parameter: list = [monat_key]
    if person_filter != "alle":
        sql += " AND u.benutzername = ?"
        parameter.append(person_filter)
    sql += " ORDER BY b.datum DESC, b.id DESC"
    zeilen = g.db.execute(sql, parameter).fetchall()

    return render_template(
        "buchungen.html",
        buchungen=zeilen,
        monat_key=monat_key,
        monat_titel=f"{MONATSNAMEN[monat - 1]} {jahr}",
        vormonat=_monat_verschieben(jahr, monat, -1),
        naechster_monat=_monat_verschieben(jahr, monat, 1),
        person_filter=person_filter,
        alle_benutzer=g.db.execute("SELECT * FROM benutzer ORDER BY id").fetchall(),
        kategorien=g.db.execute("SELECT * FROM kategorien ORDER BY art, name").fetchall(),
        heute=datetime.date.today().isoformat(),
    )


@app.route("/buchungen/<int:buchung_id>/loeschen", methods=["POST"])
@anmeldung_erforderlich
def buchung_loeschen(buchung_id: int):
    geloescht = g.db.execute("DELETE FROM buchungen WHERE id = ?", (buchung_id,)).rowcount
    g.db.commit()
    if not geloescht:
        abort(404)
    flash("Buchung gelöscht.", "ok")
    return redirect(request.referrer or url_for("buchungen"))


@app.route("/dauerauftraege", methods=["GET", "POST"])
@anmeldung_erforderlich
def dauerauftraege():
    if request.method == "POST":
        aktion = request.form.get("aktion")
        try:
            if aktion == "neu":
                art = request.form["art"]
                kategorie = g.db.execute(
                    "SELECT id FROM kategorien WHERE id = ? AND art = ?",
                    (request.form["kategorie_id"], art),
                ).fetchone()
                if not kategorie:
                    raise ValueError("Kategorie passt nicht zur gewählten Art.")
                g.db.execute(
                    "INSERT INTO dauerauftraege (benutzer_id, art, kategorie_id, betrag_cent,"
                    " beschreibung, monatstag) VALUES (?, ?, ?, ?, ?, ?)",
                    (g.benutzer["id"], art, kategorie["id"], cent(request.form["betrag"]),
                     request.form["beschreibung"].strip() or "Dauerauftrag",
                     max(1, min(28, int(request.form["monatstag"])))),
                )
                flash("Dauerauftrag angelegt.", "ok")
            elif aktion == "betrag":
                g.db.execute(
                    "UPDATE dauerauftraege SET betrag_cent = ?, aktiv = 1 WHERE id = ?",
                    (cent(request.form["betrag"]), request.form["id"]),
                )
                flash("Betrag aktualisiert und Dauerauftrag aktiviert.", "ok")
            elif aktion == "umschalten":
                g.db.execute(
                    "UPDATE dauerauftraege SET aktiv = 1 - aktiv WHERE id = ?",
                    (request.form["id"],),
                )
            elif aktion == "loeschen":
                g.db.execute("DELETE FROM dauerauftraege WHERE id = ?", (request.form["id"],))
                flash("Dauerauftrag gelöscht.", "ok")
            g.db.commit()
        except (ValueError, KeyError) as e:
            flash(f"Nicht gespeichert: {e}", "fehler")
        return redirect(url_for("dauerauftraege"))

    zeilen = g.db.execute(
        """SELECT d.*, k.name AS kategorie, u.anzeigename AS person
           FROM dauerauftraege d
           JOIN kategorien k ON k.id = d.kategorie_id
           JOIN benutzer u ON u.id = d.benutzer_id
           ORDER BY d.monatstag, d.id""",
    ).fetchall()
    return render_template(
        "dauerauftraege.html",
        dauerauftraege=zeilen,
        kategorien=g.db.execute("SELECT * FROM kategorien ORDER BY art, name").fetchall(),
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
