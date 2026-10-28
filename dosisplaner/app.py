"""Dosisplaner – Soll- und Ist-Dosis nebeneinander im Blick.

Start (Entwicklung):  python3 app.py
Im Betrieb läuft die Anwendung hinter Gunicorn, siehe deploy/.
"""
import csv
import datetime
import functools
import io
import os
import secrets
import sqlite3

from flask import (Flask, Response, abort, flash, g, redirect, render_template,
                   request, send_from_directory, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import database
from database import (AUSLOESER, BEFINDEN, SUBSTANZEN, SUBSTITUTE, SYMPTOME,
                      VERGABE, datum_de, mg, soll_fuer, soll_subst_fuer)

VERSION = "2026.10.28-2 · Substitution und Rückfälle"

MAX_LOGIN_VERSUCHE = 8

# Kleine Ermutigungen – erscheinen wechselnd auf der Startseite.
ERMUTIGUNGEN = [
    "Jeder eingetragene Tag ist ein Tag, den du bewusst gegangen bist.",
    "Nicht die Geschwindigkeit zählt, sondern die Richtung.",
    "Du machst gerade etwas, das Mut erfordert. Das ist nicht selbstverständlich.",
    "Auch ein Tag, der schwer war, ist ein Tag, den du geschafft hast.",
    "Dein Körper braucht Zeit. Die darfst du ihm geben.",
    "Überblick zu haben ist schon die halbe Strecke.",
    "Rückschritte gehören dazu. Sie löschen nichts von dem, was du geschafft hast.",
    "Du bist nicht deine Dosis. Du bist der Mensch, der sie angeht.",
]


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
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=datetime.timedelta(days=30),
)
app.jinja_env.filters["datum_de"] = datum_de
app.jinja_env.filters["mg"] = mg
app.jinja_env.globals["csrf_token"] = lambda: session.get("csrf_token", "")
app.jinja_env.globals["app_version"] = VERSION
app.jinja_env.globals["BEFINDEN"] = BEFINDEN
app.jinja_env.globals["SYMPTOME"] = SYMPTOME
app.jinja_env.globals["SUBSTITUTE"] = SUBSTITUTE
app.jinja_env.globals["VERGABE"] = VERGABE
app.jinja_env.globals["SUBSTANZEN"] = SUBSTANZEN
app.jinja_env.globals["AUSLOESER"] = AUSLOESER


@app.before_request
def vorbereiten():
    g.db = database.verbinden()
    g.benutzer = None
    if "benutzer_id" in session:
        g.benutzer = g.db.execute(
            "SELECT * FROM benutzer WHERE id = ?", (session["benutzer_id"],)
        ).fetchone()
        if g.benutzer is None:
            session.clear()
    if request.method == "POST":
        if not session.get("csrf_token") or \
                request.form.get("csrf_token") != session["csrf_token"]:
            abort(400, "Sicherheitsprüfung fehlgeschlagen. Bitte Seite neu laden.")


@app.teardown_request
def aufraeumen(fehler=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def anmeldung_erforderlich(funktion):
    @functools.wraps(funktion)
    def pruefen(*args, **kwargs):
        if g.benutzer is None:
            return redirect(url_for("login"))
        if g.benutzer["passwort_neu"] and request.endpoint != "passwort_aendern":
            return redirect(url_for("passwort_aendern"))
        return funktion(*args, **kwargs)
    return pruefen


# ---------------------------------------------------------------- Anmeldung

@app.route("/login", methods=["GET", "POST"])
def login():
    if g.benutzer:
        return redirect(url_for("start"))
    fehler = None
    if request.method == "POST":
        ip = request.remote_addr or "?"
        versuche = g.db.execute(
            "SELECT COUNT(*) AS n FROM login_versuche"
            " WHERE ip = ? AND zeit > datetime('now', '-15 minutes')", (ip,),
        ).fetchone()["n"]
        if versuche >= MAX_LOGIN_VERSUCHE:
            fehler = "Zu viele Fehlversuche. Bitte in 15 Minuten erneut versuchen."
        else:
            benutzer = g.db.execute(
                "SELECT * FROM benutzer WHERE benutzername = ?",
                (request.form.get("benutzername", "").strip().lower(),),
            ).fetchone()
            if benutzer and check_password_hash(
                    benutzer["passwort_hash"], request.form.get("passwort", "")):
                session.clear()
                session.permanent = True
                session["benutzer_id"] = benutzer["id"]
                session["csrf_token"] = secrets.token_urlsafe(32)
                g.db.execute("DELETE FROM login_versuche WHERE ip = ?", (ip,))
                g.db.commit()
                return redirect(url_for("start"))
            g.db.execute("INSERT INTO login_versuche (ip) VALUES (?)", (ip,))
            g.db.commit()
            fehler = "Benutzername oder Passwort stimmt nicht."
    if not session.get("csrf_token"):
        session["csrf_token"] = secrets.token_urlsafe(32)
    return render_template("login.html", fehler=fehler)


@app.route("/abmelden")
def abmelden():
    session.clear()
    return redirect(url_for("login"))


@app.route("/passwort", methods=["GET", "POST"])
def passwort_aendern():
    if g.benutzer is None:
        return redirect(url_for("login"))
    erzwungen = bool(g.benutzer["passwort_neu"])
    if request.method == "POST":
        neu = request.form.get("neues_passwort", "")
        if not erzwungen and not check_password_hash(
                g.benutzer["passwort_hash"], request.form.get("aktuelles_passwort", "")):
            flash("Das aktuelle Passwort stimmt nicht.", "fehler")
        elif len(neu) < 8:
            flash("Das neue Passwort braucht mindestens 8 Zeichen.", "fehler")
        elif neu != request.form.get("wiederholung", ""):
            flash("Die beiden Eingaben stimmen nicht überein.", "fehler")
        else:
            g.db.execute(
                "UPDATE benutzer SET passwort_hash = ?, passwort_neu = 0 WHERE id = ?",
                (generate_password_hash(neu), g.benutzer["id"]),
            )
            g.db.commit()
            flash("Passwort gespeichert.", "ok")
            return redirect(url_for("start"))
    return render_template("passwort.html", erzwungen=erzwungen)


# ------------------------------------------------------------------- Helfer

def _verlauf(tage: int = 60) -> list:
    """Soll und Ist der letzten Tage nebeneinander – Grundlage für Diagramm
    und Tabelle."""
    heute = datetime.date.today()
    start = heute - datetime.timedelta(days=tage - 1)
    eintraege = {
        z["datum"]: z for z in g.db.execute(
            "SELECT * FROM eintraege WHERE datum BETWEEN ? AND ?",
            (start.isoformat(), heute.isoformat()),
        )
    }
    # Rückfalltage werden im Diagramm als Markierung gezeigt – so sieht man,
    # ob sie mit Ausschlägen bei der Dosis zusammenfallen.
    konsum_tage = {
        z["datum"] for z in g.db.execute(
            "SELECT DISTINCT datum FROM konsum WHERE datum BETWEEN ? AND ?",
            (start.isoformat(), heute.isoformat()),
        )
    }
    reihe = []
    for versatz in range(tage):
        tag = start + datetime.timedelta(days=versatz)
        iso = tag.isoformat()
        eintrag = eintraege.get(iso)
        soll = soll_fuer(g.db, iso)
        ist = eintrag["ist_mg"] if eintrag else None
        reihe.append({
            "datum": iso,
            "kurz": f"{tag.day:02d}.{tag.month:02d}.",
            "soll": soll,
            "ist": ist,
            "differenz": (ist - soll) if (ist is not None and soll is not None) else None,
            "befinden": eintrag["befinden"] if eintrag else None,
            "symptome": eintrag["symptome"] if eintrag else "",
            "notiz": eintrag["notiz"] if eintrag else "",
            "konsum": iso in konsum_tage,
            "heute": iso == heute.isoformat(),
        })
    return reihe


def _kennzahlen() -> dict:
    """Startdosis, aktueller Stand und wie weit du schon gekommen bist."""
    erster = g.db.execute(
        "SELECT ist_mg, datum FROM eintraege ORDER BY datum LIMIT 1").fetchone()
    letzter = g.db.execute(
        "SELECT ist_mg, datum FROM eintraege ORDER BY datum DESC LIMIT 1").fetchone()
    ziel = g.db.execute(
        "SELECT soll_mg FROM plan_phasen ORDER BY bis DESC LIMIT 1").fetchone()

    start_mg = erster["ist_mg"] if erster else None
    aktuell_mg = letzter["ist_mg"] if letzter else None
    ziel_mg = ziel["soll_mg"] if ziel else 0.0

    fortschritt = None
    if start_mg is not None and aktuell_mg is not None and start_mg > ziel_mg:
        fortschritt = round((start_mg - aktuell_mg) / (start_mg - ziel_mg) * 100)
        fortschritt = max(0, min(100, fortschritt))

    return {
        "start_mg": start_mg,
        "start_datum": erster["datum"] if erster else None,
        "aktuell_mg": aktuell_mg,
        "aktuell_datum": letzter["datum"] if letzter else None,
        "ziel_mg": ziel_mg,
        "reduziert_mg": (start_mg - aktuell_mg)
                        if (start_mg is not None and aktuell_mg is not None) else None,
        "fortschritt": fortschritt,
        "tage_dabei": g.db.execute(
            "SELECT COUNT(*) AS n FROM eintraege").fetchone()["n"],
    }


def _serie_ohne_luecke() -> int:
    """Wie viele Tage am Stück zuletzt eingetragen wurden."""
    tage = [z["datum"] for z in g.db.execute(
        "SELECT datum FROM eintraege ORDER BY datum DESC LIMIT 400")]
    if not tage:
        return 0
    heute = datetime.date.today()
    letzter = datetime.date.fromisoformat(tage[0])
    # Die Serie zählt nur, wenn heute oder gestern eingetragen wurde.
    if (heute - letzter).days > 1:
        return 0
    serie, vorheriger = 1, letzter
    for iso in tage[1:]:
        tag = datetime.date.fromisoformat(iso)
        if (vorheriger - tag).days == 1:
            serie += 1
            vorheriger = tag
        else:
            break
    return serie


# -------------------------------------------------------------------- Seiten

@app.route("/", methods=["GET", "POST"])
@anmeldung_erforderlich
def start():
    if request.method == "POST":
        try:
            datum = datetime.date.fromisoformat(request.form["datum"]).isoformat()
            ist = float(request.form["ist_mg"].replace(",", "."))
            if ist < 0:
                raise ValueError("Die Dosis kann nicht unter 0 liegen.")
            befinden = request.form.get("befinden") or None
            symptome = ", ".join(request.form.getlist("symptome"))
            # Ein Eintrag pro Tag: vorhandenen überschreiben statt doppeln.
            g.db.execute(
                """INSERT INTO eintraege (datum, ist_mg, befinden, symptome, notiz)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(datum) DO UPDATE SET
                     ist_mg = excluded.ist_mg, befinden = excluded.befinden,
                     symptome = excluded.symptome, notiz = excluded.notiz""",
                (datum, ist, befinden, symptome,
                 request.form.get("notiz", "").strip()),
            )
            g.db.commit()
            flash("Eingetragen. Gut, dass du drangeblieben bist.", "ok")
        except (ValueError, KeyError, sqlite3.Error) as e:
            g.db.rollback()
            flash(f"Nicht gespeichert: {e}", "fehler")
        return redirect(url_for("start"))

    heute = datetime.date.today().isoformat()
    heute_eintrag = g.db.execute(
        "SELECT * FROM eintraege WHERE datum = ?", (heute,)).fetchone()
    verlauf = _verlauf(60)
    kennzahlen = _kennzahlen()

    # Abweichung der letzten 7 Tage, in denen etwas eingetragen wurde.
    letzte = [t for t in verlauf if t["differenz"] is not None][-7:]
    abweichung = round(sum(t["differenz"] for t in letzte) / len(letzte), 1) if letzte else None

    return render_template(
        "start.html",
        heute=heute,
        heute_eintrag=heute_eintrag,
        soll_heute=soll_fuer(g.db, heute),
        kennzahlen=kennzahlen,
        serie=_serie_ohne_luecke(),
        abweichung=abweichung,
        verlauf=verlauf,
        letzte_tage=list(reversed(verlauf[-14:])),
        ermutigung=ERMUTIGUNGEN[datetime.date.today().toordinal() % len(ERMUTIGUNGEN)],
        hat_plan=bool(g.db.execute(
            "SELECT 1 FROM plan_phasen LIMIT 1").fetchone()),
        # Substitutionsmittel, für die heute noch nichts eingetragen ist –
        # aber nur solche, für die überhaupt eine Verordnung hinterlegt ist.
        subst_offen=[
            name for schluessel, (name, _) in SUBSTITUTE.items()
            if g.db.execute("SELECT 1 FROM subst_plan WHERE mittel = ? LIMIT 1",
                            (schluessel,)).fetchone()
            and not g.db.execute(
                "SELECT 1 FROM subst_eintraege WHERE mittel = ? AND datum = ?",
                (schluessel, heute)).fetchone()
        ],
        erfolge=g.db.execute(
            "SELECT * FROM erfolge ORDER BY datum DESC, id DESC LIMIT 5").fetchall(),
    )


@app.route("/plan", methods=["GET", "POST"])
@anmeldung_erforderlich
def plan():
    if request.method == "POST":
        try:
            aktion = request.form.get("aktion")
            if aktion == "neu":
                von = datetime.date.fromisoformat(request.form["von"])
                bis = datetime.date.fromisoformat(request.form["bis"])
                if bis < von:
                    raise ValueError("Das Ende liegt vor dem Beginn.")
                soll = float(request.form["soll_mg"].replace(",", "."))
                if soll < 0:
                    raise ValueError("Die Dosis kann nicht unter 0 liegen.")
                g.db.execute(
                    "INSERT INTO plan_phasen (von, bis, soll_mg, notiz)"
                    " VALUES (?, ?, ?, ?)",
                    (von.isoformat(), bis.isoformat(), soll,
                     request.form.get("notiz", "").strip()),
                )
                flash("Abschnitt gespeichert.", "ok")
            elif aktion == "loeschen":
                g.db.execute("DELETE FROM plan_phasen WHERE id = ?", (request.form["id"],))
                flash("Abschnitt gelöscht.", "ok")
            g.db.commit()
        except (ValueError, KeyError, sqlite3.Error) as e:
            g.db.rollback()
            flash(f"Nicht gespeichert: {e}", "fehler")
        return redirect(url_for("plan"))

    phasen = g.db.execute("SELECT * FROM plan_phasen ORDER BY von").fetchall()
    # Lücken und Überschneidungen zwischen Abschnitten finden.
    hinweise = []
    for vorher, nachher in zip(phasen, phasen[1:]):
        ende = datetime.date.fromisoformat(vorher["bis"])
        start_naechste = datetime.date.fromisoformat(nachher["von"])
        abstand = (start_naechste - ende).days
        if abstand > 1:
            hinweise.append(
                f"Zwischen {datum_de(vorher['bis'])} und {datum_de(nachher['von'])} "
                f"fehlt ein Abschnitt ({abstand - 1} Tage ohne Soll-Wert).")
        elif abstand < 1:
            hinweise.append(
                f"Die Abschnitte ab {datum_de(vorher['von'])} und "
                f"{datum_de(nachher['von'])} überschneiden sich.")

    heute = datetime.date.today()
    return render_template(
        "plan.html",
        phasen=phasen,
        hinweise=hinweise,
        heute=heute.isoformat(),
        morgen=(heute + datetime.timedelta(days=1)).isoformat(),
        soll_heute=soll_fuer(g.db, heute.isoformat()),
    )


@app.route("/verlauf")
@anmeldung_erforderlich
def verlauf():
    try:
        tage = max(7, min(365, int(request.args.get("tage", 60))))
    except ValueError:
        tage = 60

    reihe = _verlauf(tage)
    eingetragen = [t for t in reihe if t["ist"] is not None]

    if request.args.get("export") == "csv":
        puffer = io.StringIO()
        schreiber = csv.writer(puffer, delimiter=";")
        schreiber.writerow(["Datum", "Soll (mg)", "Ist (mg)", "Abweichung (mg)",
                            "Befinden", "Symptome", "Notiz"])
        for t in reihe:
            if t["ist"] is None and t["soll"] is None:
                continue
            schreiber.writerow([
                datum_de(t["datum"]),
                str(t["soll"]).replace(".", ",") if t["soll"] is not None else "",
                str(t["ist"]).replace(".", ",") if t["ist"] is not None else "",
                str(t["differenz"]).replace(".", ",") if t["differenz"] is not None else "",
                BEFINDEN.get(t["befinden"], ("", ""))[0] if t["befinden"] else "",
                t["symptome"], t["notiz"],
            ])
        antwort = Response("﻿" + puffer.getvalue(),
                           mimetype="text/csv; charset=utf-8")
        antwort.headers["Content-Disposition"] = \
            f"attachment; filename=dosisverlauf-{datetime.date.today()}.csv"
        return antwort

    # Häufigste Symptome im Zeitraum – hilfreich fürs Arztgespräch.
    haeufigkeit: dict = {}
    for t in eingetragen:
        for s in filter(None, (x.strip() for x in t["symptome"].split(","))):
            haeufigkeit[s] = haeufigkeit.get(s, 0) + 1
    top_symptome = sorted(haeufigkeit.items(), key=lambda p: p[1], reverse=True)[:6]

    befinden_werte = [t["befinden"] for t in eingetragen if t["befinden"]]
    return render_template(
        "verlauf.html",
        reihe=reihe,
        tabelle=list(reversed([t for t in reihe if t["ist"] is not None or t["soll"] is not None])),
        tage=tage,
        anzahl=len(eingetragen),
        top_symptome=top_symptome,
        befinden_schnitt=round(sum(befinden_werte) / len(befinden_werte), 1)
                         if befinden_werte else None,
        kennzahlen=_kennzahlen(),
    )


# ------------------------------------------------------------- Substitution

def _subst_reihe(mittel: str, tage: int) -> list:
    """Verordnet und tatsächlich, Tag für Tag, für ein Substitutionsmittel."""
    heute = datetime.date.today()
    start = heute - datetime.timedelta(days=tage - 1)
    eintraege = {
        z["datum"]: z for z in g.db.execute(
            "SELECT * FROM subst_eintraege WHERE mittel = ? AND datum BETWEEN ? AND ?",
            (mittel, start.isoformat(), heute.isoformat()),
        )
    }
    reihe = []
    for versatz in range(tage):
        tag = start + datetime.timedelta(days=versatz)
        iso = tag.isoformat()
        eintrag = eintraege.get(iso)
        soll = soll_subst_fuer(g.db, mittel, iso)
        ist = eintrag["ist_mg"] if eintrag else None
        reihe.append({
            "datum": iso,
            "kurz": f"{tag.day:02d}.{tag.month:02d}.",
            "soll": soll,
            "ist": ist,
            "differenz": (ist - soll) if (ist is not None and soll is not None) else None,
            "vergabe": eintrag["vergabe"] if eintrag else "",
            "notiz": eintrag["notiz"] if eintrag else "",
            "heute": iso == heute.isoformat(),
        })
    return reihe


@app.route("/substitution", methods=["GET", "POST"])
@anmeldung_erforderlich
def substitution():
    if request.method == "POST":
        try:
            aktion = request.form.get("aktion")
            mittel = request.form.get("mittel", "")
            if mittel not in SUBSTITUTE:
                raise ValueError("Unbekanntes Mittel.")

            if aktion == "eintrag":
                datum = datetime.date.fromisoformat(request.form["datum"]).isoformat()
                ist = float(request.form["ist_mg"].replace(",", "."))
                if ist < 0:
                    raise ValueError("Die Dosis kann nicht unter 0 liegen.")
                vergabe = request.form.get("vergabe", "")
                if vergabe and vergabe not in VERGABE:
                    raise ValueError("Unbekannte Vergabeform.")
                g.db.execute(
                    """INSERT INTO subst_eintraege (datum, mittel, ist_mg, vergabe, notiz)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(datum, mittel) DO UPDATE SET
                         ist_mg = excluded.ist_mg, vergabe = excluded.vergabe,
                         notiz = excluded.notiz""",
                    (datum, mittel, ist, vergabe, request.form.get("notiz", "").strip()),
                )
                flash(f"{SUBSTITUTE[mittel][0]} eingetragen.", "ok")

            elif aktion == "verordnung":
                von = datetime.date.fromisoformat(request.form["von"])
                bis = datetime.date.fromisoformat(request.form["bis"])
                if bis < von:
                    raise ValueError("Das Ende liegt vor dem Beginn.")
                soll = float(request.form["soll_mg"].replace(",", "."))
                if soll < 0:
                    raise ValueError("Die Dosis kann nicht unter 0 liegen.")
                g.db.execute(
                    "INSERT INTO subst_plan (mittel, von, bis, soll_mg, notiz)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (mittel, von.isoformat(), bis.isoformat(), soll,
                     request.form.get("notiz", "").strip()),
                )
                flash("Verordnung festgehalten.", "ok")

            elif aktion == "verordnung_loeschen":
                g.db.execute("DELETE FROM subst_plan WHERE id = ?", (request.form["id"],))
                flash("Eintrag gelöscht.", "ok")

            elif aktion == "eintrag_loeschen":
                g.db.execute("DELETE FROM subst_eintraege WHERE id = ?",
                             (request.form["id"],))
                flash("Eintrag gelöscht.", "ok")
            g.db.commit()
        except (ValueError, KeyError, sqlite3.Error) as e:
            g.db.rollback()
            flash(f"Nicht gespeichert: {e}", "fehler")
        return redirect(url_for("substitution"))

    try:
        tage = max(7, min(365, int(request.args.get("tage", 30))))
    except ValueError:
        tage = 30
    heute = datetime.date.today().isoformat()

    if request.args.get("export") == "csv":
        puffer = io.StringIO()
        schreiber = csv.writer(puffer, delimiter=";")
        schreiber.writerow(["Datum", "Mittel", "Verordnet (mg)", "Genommen (mg)",
                            "Abweichung (mg)", "Vergabe", "Notiz"])
        zeilen: dict = {}
        for schluessel, (name, _) in SUBSTITUTE.items():
            for t in _subst_reihe(schluessel, tage):
                if t["ist"] is None and t["soll"] is None:
                    continue
                zeilen.setdefault(t["datum"], []).append((name, t))
        for datum in sorted(zeilen):
            for name, t in zeilen[datum]:
                schreiber.writerow([
                    datum_de(datum), name,
                    str(t["soll"]).replace(".", ",") if t["soll"] is not None else "",
                    str(t["ist"]).replace(".", ",") if t["ist"] is not None else "",
                    str(t["differenz"]).replace(".", ",") if t["differenz"] is not None else "",
                    t["vergabe"], t["notiz"],
                ])
        antwort = Response("﻿" + puffer.getvalue(),
                           mimetype="text/csv; charset=utf-8")
        antwort.headers["Content-Disposition"] = \
            f"attachment; filename=substitution-{datetime.date.today()}.csv"
        return antwort

    mittel_daten = []
    for schluessel, (name, wirkstoff) in SUBSTITUTE.items():
        reihe = _subst_reihe(schluessel, tage)
        eingetragen = [t for t in reihe if t["ist"] is not None]
        mittel_daten.append({
            "schluessel": schluessel,
            "name": name,
            "wirkstoff": wirkstoff,
            "reihe": reihe,
            "letzte_tage": list(reversed(reihe))[:14],
            "heute": next((t for t in reihe if t["heute"]), None),
            "soll_heute": soll_subst_fuer(g.db, schluessel, heute),
            "anzahl": len(eingetragen),
            "verordnungen": g.db.execute(
                "SELECT * FROM subst_plan WHERE mittel = ? ORDER BY von DESC",
                (schluessel,)).fetchall(),
            "eintrag_heute": g.db.execute(
                "SELECT * FROM subst_eintraege WHERE mittel = ? AND datum = ?",
                (schluessel, heute)).fetchone(),
        })

    return render_template("substitution.html", mittel_daten=mittel_daten,
                           tage=tage, heute=heute)


# ------------------------------------------------------------------ Rückfälle

def _konsum_kennzahlen() -> dict:
    """Wie lange ist es her, und wie lange war die längste Strecke."""
    tage = [datetime.date.fromisoformat(z["datum"]) for z in g.db.execute(
        "SELECT DISTINCT datum FROM konsum ORDER BY datum")]
    heute = datetime.date.today()
    if not tage:
        return {"anzahl": 0, "letzter": None, "seither": None, "laengste": None}

    # Längste Strecke zwischen zwei Einträgen – und die aktuelle zählt mit.
    abstaende = [(b - a).days for a, b in zip(tage, tage[1:])]
    seither = (heute - tage[-1]).days
    return {
        "anzahl": g.db.execute("SELECT COUNT(*) AS n FROM konsum").fetchone()["n"],
        "letzter": tage[-1].isoformat(),
        "seither": seither,
        "laengste": max(abstaende + [seither]) if (abstaende or seither) else None,
    }


@app.route("/konsum", methods=["GET", "POST"])
@anmeldung_erforderlich
def konsum():
    if request.method == "POST":
        try:
            aktion = request.form.get("aktion")
            if aktion == "neu":
                datum = datetime.date.fromisoformat(request.form["datum"])
                if datum > datetime.date.today():
                    raise ValueError("Das Datum liegt in der Zukunft.")
                substanz = request.form.get("substanz", "").strip()
                if not substanz:
                    raise ValueError("Bitte angeben, worum es ging.")
                g.db.execute(
                    """INSERT INTO konsum (datum, uhrzeit, substanz, menge,
                                           ausloeser, davor, danach, besprochen, notiz)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (datum.isoformat(),
                     request.form.get("uhrzeit", "").strip(),
                     substanz,
                     request.form.get("menge", "").strip(),
                     ", ".join(request.form.getlist("ausloeser")),
                     request.form.get("davor") or None,
                     request.form.get("danach") or None,
                     request.form.get("besprochen", ""),
                     request.form.get("notiz", "").strip()),
                )
                flash("Eingetragen. Dass du es aufschreibst, ist der schwere Teil.", "ok")
            elif aktion == "besprochen":
                g.db.execute("UPDATE konsum SET besprochen = 'ja' WHERE id = ?",
                             (request.form["id"],))
                flash("Als besprochen vermerkt.", "ok")
            elif aktion == "loeschen":
                g.db.execute("DELETE FROM konsum WHERE id = ?", (request.form["id"],))
                flash("Eintrag gelöscht.", "ok")
            g.db.commit()
        except (ValueError, KeyError, sqlite3.Error) as e:
            g.db.rollback()
            flash(f"Nicht gespeichert: {e}", "fehler")
        return redirect(url_for("konsum"))

    eintraege = g.db.execute(
        "SELECT * FROM konsum ORDER BY datum DESC, id DESC").fetchall()

    if request.args.get("export") == "csv":
        puffer = io.StringIO()
        schreiber = csv.writer(puffer, delimiter=";")
        schreiber.writerow(["Datum", "Uhrzeit", "Substanz", "Menge", "Auslöser",
                            "Befinden davor", "Befinden danach", "Besprochen", "Notiz"])
        for e in reversed(eintraege):
            schreiber.writerow([
                datum_de(e["datum"]), e["uhrzeit"], e["substanz"], e["menge"],
                e["ausloeser"],
                BEFINDEN.get(e["davor"], ("", ""))[0] if e["davor"] else "",
                BEFINDEN.get(e["danach"], ("", ""))[0] if e["danach"] else "",
                e["besprochen"], e["notiz"],
            ])
        antwort = Response("﻿" + puffer.getvalue(),
                           mimetype="text/csv; charset=utf-8")
        antwort.headers["Content-Disposition"] = \
            f"attachment; filename=rueckfaelle-{datetime.date.today()}.csv"
        return antwort

    # Häufigste Auslöser – darum geht es hier eigentlich.
    haeufigkeit: dict = {}
    for e in eintraege:
        for a in filter(None, (x.strip() for x in e["ausloeser"].split(","))):
            haeufigkeit[a] = haeufigkeit.get(a, 0) + 1
    top_ausloeser = sorted(haeufigkeit.items(), key=lambda p: p[1], reverse=True)[:8]

    return render_template(
        "konsum.html",
        eintraege=eintraege,
        kennzahlen=_konsum_kennzahlen(),
        top_ausloeser=top_ausloeser,
        heute=datetime.date.today().isoformat(),
    )


@app.route("/erfolge", methods=["GET", "POST"])
@anmeldung_erforderlich
def erfolge():
    if request.method == "POST":
        try:
            aktion = request.form.get("aktion")
            if aktion == "neu":
                text = request.form["text"].strip()
                if not text:
                    raise ValueError("Bitte etwas eintragen.")
                g.db.execute(
                    "INSERT INTO erfolge (datum, text) VALUES (?, ?)",
                    (datetime.date.fromisoformat(request.form["datum"]).isoformat(), text),
                )
                flash("Festgehalten. 🌱", "ok")
            elif aktion == "loeschen":
                g.db.execute("DELETE FROM erfolge WHERE id = ?", (request.form["id"],))
            g.db.commit()
        except (ValueError, KeyError, sqlite3.Error) as e:
            g.db.rollback()
            flash(f"Nicht gespeichert: {e}", "fehler")
        return redirect(url_for("erfolge"))

    return render_template(
        "erfolge.html",
        eintraege=g.db.execute(
            "SELECT * FROM erfolge ORDER BY datum DESC, id DESC").fetchall(),
        heute=datetime.date.today().isoformat(),
    )


@app.route("/hilfe")
def hilfe():
    """Anlaufstellen – auch ohne Anmeldung erreichbar."""
    return render_template("hilfe.html")


@app.route("/sw.js")
def service_worker():
    antwort = send_from_directory(app.static_folder, "sw.js")
    antwort.headers["Content-Type"] = "application/javascript; charset=utf-8"
    antwort.headers["Cache-Control"] = "no-cache"
    return antwort


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5002)), debug=False)
