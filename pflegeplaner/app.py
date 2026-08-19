"""Pflegeplaner – Kalender, Visiten und Übergaben für das Pflegeteam.

Start (Entwicklung):  python3 app.py
Im Betrieb läuft die Anwendung hinter Gunicorn, siehe deploy/.
"""
import datetime
import functools
import os
import secrets
import sqlite3

from flask import (Flask, abort, flash, g, redirect, render_template,
                   request, send_from_directory, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import database
from database import (MONATSNAMEN, SCHICHTEN, TERMINARTEN, WOCHENTAGE,
                      datum_de, montag_der_woche)

# Sichtbare Version – erscheint unten auf jeder Seite. So ist nach einem
# Update sofort erkennbar, ob der neue Stand wirklich läuft.
VERSION = "2026.08.18-1 · Kalender, Visiten, Übergaben"

# Anmeldeversuche: nach so vielen Fehlversuchen je Viertelstunde ist Schluss.
MAX_LOGIN_VERSUCHE = 8


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
    PERMANENT_SESSION_LIFETIME=datetime.timedelta(days=14),
)
app.jinja_env.filters["datum_de"] = datum_de
app.jinja_env.globals["csrf_token"] = lambda: session.get("csrf_token", "")
app.jinja_env.globals["app_version"] = VERSION
app.jinja_env.globals["terminarten"] = TERMINARTEN
app.jinja_env.globals["tsymbol"] = lambda art: TERMINARTEN.get(art, "📌")


@app.before_request
def vorbereiten():
    g.db = database.verbinden()
    g.benutzer = None
    if "benutzer_id" in session:
        g.benutzer = g.db.execute(
            "SELECT * FROM benutzer WHERE id = ? AND aktiv = 1",
            (session["benutzer_id"],),
        ).fetchone()
        if g.benutzer is None:
            session.clear()

    # Jede ändernde Anfrage muss den Sitzungsschlüssel mitschicken (CSRF-Schutz).
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
            return redirect(url_for("login", weiter=request.path))
        # Startpasswort muss zuerst geändert werden.
        if g.benutzer["passwort_neu"] and request.endpoint != "passwort_aendern":
            return redirect(url_for("passwort_aendern"))
        return funktion(*args, **kwargs)
    return pruefen


def leitung_erforderlich(funktion):
    """Für Verwaltungsseiten (Team, Bewohner, Ärzte)."""
    @functools.wraps(funktion)
    def pruefen(*args, **kwargs):
        if g.benutzer is None:
            return redirect(url_for("login", weiter=request.path))
        if g.benutzer["rolle"] != "leitung":
            flash("Dieser Bereich ist der Leitung vorbehalten.", "fehler")
            return redirect(url_for("kalender"))
        return funktion(*args, **kwargs)
    return pruefen


# ---------------------------------------------------------------- Anmeldung

@app.route("/login", methods=["GET", "POST"])
def login():
    if g.benutzer:
        return redirect(url_for("kalender"))
    fehler = None
    if request.method == "POST":
        benutzername = request.form.get("benutzername", "").strip().lower()
        ip = request.remote_addr or "?"
        versuche = g.db.execute(
            "SELECT COUNT(*) AS n FROM login_versuche"
            " WHERE ip = ? AND zeit > datetime('now', '-15 minutes')",
            (ip,),
        ).fetchone()["n"]
        if versuche >= MAX_LOGIN_VERSUCHE:
            fehler = "Zu viele Fehlversuche. Bitte in 15 Minuten erneut versuchen."
        else:
            benutzer = g.db.execute(
                "SELECT * FROM benutzer WHERE benutzername = ? AND aktiv = 1",
                (benutzername,),
            ).fetchone()
            if benutzer and check_password_hash(
                    benutzer["passwort_hash"], request.form.get("passwort", "")):
                session.clear()
                session.permanent = True
                session["benutzer_id"] = benutzer["id"]
                session["csrf_token"] = secrets.token_urlsafe(32)
                g.db.execute("DELETE FROM login_versuche WHERE ip = ?", (ip,))
                g.db.commit()
                ziel = request.args.get("weiter", "")
                return redirect(ziel if ziel.startswith("/") else url_for("kalender"))
            g.db.execute(
                "INSERT INTO login_versuche (benutzername, ip) VALUES (?, ?)",
                (benutzername, ip),
            )
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
            flash("Die beiden neuen Passwörter stimmen nicht überein.", "fehler")
        else:
            g.db.execute(
                "UPDATE benutzer SET passwort_hash = ?, passwort_neu = 0 WHERE id = ?",
                (generate_password_hash(neu), g.benutzer["id"]),
            )
            g.db.commit()
            flash("Passwort gespeichert.", "ok")
            return redirect(url_for("kalender"))
    return render_template("passwort.html", erzwungen=erzwungen)


# ----------------------------------------------------------------- Kalender

def _woche_aus_request() -> datetime.date:
    """Montag der angezeigten Woche; ohne Angabe die laufende Woche."""
    try:
        return montag_der_woche(datetime.date.fromisoformat(request.args["woche"]))
    except (ValueError, KeyError):
        return montag_der_woche(datetime.date.today())


def _termine_der_woche(montag: datetime.date) -> dict:
    sonntag = montag + datetime.timedelta(days=6)
    zeilen = g.db.execute(
        """SELECT t.*, b.name AS bewohner, b.zimmer, a.name AS arzt,
                  a.fachrichtung
           FROM termine t
           LEFT JOIN bewohner b ON b.id = t.bewohner_id
           LEFT JOIN aerzte  a ON a.id = t.arzt_id
           WHERE t.datum BETWEEN ? AND ?
           ORDER BY t.datum, (t.uhrzeit = ''), t.uhrzeit, t.id""",
        (montag.isoformat(), sonntag.isoformat()),
    ).fetchall()
    nach_tag: dict = {}
    for t in zeilen:
        nach_tag.setdefault(t["datum"], []).append(t)
    return nach_tag


@app.route("/", methods=["GET", "POST"])
@anmeldung_erforderlich
def kalender():
    if request.method == "POST":
        try:
            datum = datetime.date.fromisoformat(request.form["datum"]).isoformat()
            uhrzeit = request.form.get("uhrzeit", "").strip()
            if uhrzeit:  # auf gültige Uhrzeit prüfen
                datetime.time.fromisoformat(uhrzeit)
            art = request.form.get("art", "Sonstiges")
            if art not in TERMINARTEN:
                raise ValueError("Unbekannte Terminart.")
            g.db.execute(
                """INSERT INTO termine (datum, uhrzeit, art, bewohner_id, arzt_id,
                                        titel, notiz, angelegt_von)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (datum, uhrzeit, art,
                 request.form.get("bewohner_id") or None,
                 request.form.get("arzt_id") or None,
                 request.form.get("titel", "").strip(),
                 request.form.get("notiz", "").strip(),
                 g.benutzer["id"]),
            )
            g.db.commit()
            flash("Termin eingetragen.", "ok")
        except (ValueError, KeyError, sqlite3.Error) as e:
            g.db.rollback()
            flash(f"Termin nicht gespeichert: {e}", "fehler")
        return redirect(url_for("kalender", woche=request.form.get("datum", "")))

    montag = _woche_aus_request()
    nach_tag = _termine_der_woche(montag)
    heute = datetime.date.today().isoformat()

    tage = []
    for versatz in range(7):
        tag = montag + datetime.timedelta(days=versatz)
        iso = tag.isoformat()
        tage.append({
            "iso": iso,
            "name": WOCHENTAGE[versatz],
            "kurz": f"{tag.day:02d}.{tag.month:02d}.",
            "termine": nach_tag.get(iso, []),
            "heute": iso == heute,
            "wochenende": versatz >= 5,
        })

    sonntag = montag + datetime.timedelta(days=6)
    kw = montag.isocalendar()[1]
    return render_template(
        "kalender.html",
        tage=tage,
        kalenderwoche=kw,
        zeitraum=f"{montag.day:02d}.{montag.month:02d}. – "
                 f"{sonntag.day:02d}.{sonntag.month:02d}.{sonntag.year}",
        vorwoche=(montag - datetime.timedelta(days=7)).isoformat(),
        naechste_woche=(montag + datetime.timedelta(days=7)).isoformat(),
        diese_woche=montag_der_woche(datetime.date.today()).isoformat(),
        heute=heute,
        bewohner=g.db.execute(
            "SELECT * FROM bewohner WHERE aktiv = 1 ORDER BY zimmer, name").fetchall(),
        aerzte=g.db.execute(
            "SELECT * FROM aerzte WHERE aktiv = 1 ORDER BY name").fetchall(),
    )


@app.route("/termin/<int:termin_id>/erledigt", methods=["POST"])
@anmeldung_erforderlich
def termin_erledigt(termin_id: int):
    g.db.execute("UPDATE termine SET erledigt = 1 - erledigt WHERE id = ?", (termin_id,))
    g.db.commit()
    return redirect(request.referrer or url_for("kalender"))


@app.route("/termin/<int:termin_id>/loeschen", methods=["POST"])
@anmeldung_erforderlich
def termin_loeschen(termin_id: int):
    try:
        g.db.execute("DELETE FROM termine WHERE id = ?", (termin_id,))
        g.db.commit()
        flash("Termin gelöscht.", "ok")
    except sqlite3.Error as e:
        g.db.rollback()
        flash(f"Nicht gelöscht: {e}", "fehler")
    return redirect(request.referrer or url_for("kalender"))


@app.route("/termin/<int:termin_id>/bearbeiten", methods=["GET", "POST"])
@anmeldung_erforderlich
def termin_bearbeiten(termin_id: int):
    termin = g.db.execute("SELECT * FROM termine WHERE id = ?", (termin_id,)).fetchone()
    if not termin:
        abort(404)
    if request.method == "POST":
        try:
            uhrzeit = request.form.get("uhrzeit", "").strip()
            if uhrzeit:
                datetime.time.fromisoformat(uhrzeit)
            art = request.form.get("art", "Sonstiges")
            if art not in TERMINARTEN:
                raise ValueError("Unbekannte Terminart.")
            datum = datetime.date.fromisoformat(request.form["datum"]).isoformat()
            g.db.execute(
                """UPDATE termine SET datum = ?, uhrzeit = ?, art = ?, bewohner_id = ?,
                          arzt_id = ?, titel = ?, notiz = ? WHERE id = ?""",
                (datum, uhrzeit, art,
                 request.form.get("bewohner_id") or None,
                 request.form.get("arzt_id") or None,
                 request.form.get("titel", "").strip(),
                 request.form.get("notiz", "").strip(), termin_id),
            )
            g.db.commit()
            flash("Termin aktualisiert.", "ok")
            return redirect(url_for("kalender", woche=datum))
        except (ValueError, KeyError, sqlite3.Error) as e:
            g.db.rollback()
            flash(f"Nicht gespeichert: {e}", "fehler")
    return render_template(
        "termin_bearbeiten.html",
        termin=termin,
        bewohner=g.db.execute(
            "SELECT * FROM bewohner WHERE aktiv = 1 ORDER BY zimmer, name").fetchall(),
        aerzte=g.db.execute(
            "SELECT * FROM aerzte WHERE aktiv = 1 ORDER BY name").fetchall(),
    )


# ------------------------------------------------------------------ Visiten

@app.route("/visiten", methods=["GET", "POST"])
@anmeldung_erforderlich
def visiten():
    """Ärzteverzeichnis und die anstehenden Visiten der nächsten 14 Tage."""
    if request.method == "POST":
        try:
            aktion = request.form.get("aktion")
            if aktion == "neu":
                name = request.form["name"].strip()
                if not name:
                    raise ValueError("Bitte einen Namen angeben.")
                g.db.execute(
                    """INSERT INTO aerzte (name, fachrichtung, telefon, visitentag, hinweis)
                       VALUES (?, ?, ?, ?, ?)""",
                    (name, request.form.get("fachrichtung", "").strip(),
                     request.form.get("telefon", "").strip(),
                     request.form.get("visitentag", "").strip(),
                     request.form.get("hinweis", "").strip()),
                )
                flash("Eintrag angelegt.", "ok")
            elif aktion == "loeschen":
                # Termine bleiben erhalten, verlieren aber die Zuordnung.
                arzt_id = request.form["id"]
                g.db.execute("UPDATE termine SET arzt_id = NULL WHERE arzt_id = ?", (arzt_id,))
                g.db.execute("DELETE FROM aerzte WHERE id = ?", (arzt_id,))
                flash("Eintrag gelöscht.", "ok")
            g.db.commit()
        except (ValueError, KeyError, sqlite3.Error) as e:
            g.db.rollback()
            flash(f"Nicht gespeichert: {e}", "fehler")
        return redirect(url_for("visiten"))

    heute = datetime.date.today()
    bis = heute + datetime.timedelta(days=14)
    anstehend = g.db.execute(
        """SELECT t.*, b.name AS bewohner, b.zimmer, a.name AS arzt, a.fachrichtung
           FROM termine t
           LEFT JOIN bewohner b ON b.id = t.bewohner_id
           LEFT JOIN aerzte  a ON a.id = t.arzt_id
           WHERE t.datum BETWEEN ? AND ? AND t.art IN ('Visite', 'Arzttermin')
           ORDER BY t.datum, (t.uhrzeit = ''), t.uhrzeit""",
        (heute.isoformat(), bis.isoformat()),
    ).fetchall()

    return render_template(
        "visiten.html",
        aerzte=g.db.execute(
            "SELECT * FROM aerzte WHERE aktiv = 1 ORDER BY name").fetchall(),
        anstehend=anstehend,
        wochentage=WOCHENTAGE,
    )


# ---------------------------------------------------------------- Übergaben

@app.route("/uebergaben", methods=["GET", "POST"])
@anmeldung_erforderlich
def uebergaben():
    if request.method == "POST":
        try:
            text = request.form.get("text", "").strip()
            if not text:
                raise ValueError("Bitte einen Text eingeben.")
            schicht = request.form.get("schicht", SCHICHTEN[0])
            if schicht not in SCHICHTEN:
                raise ValueError("Unbekannte Schicht.")
            g.db.execute(
                """INSERT INTO uebergaben (datum, schicht, bewohner_id, text,
                                           wichtig, verfasser_id)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (datetime.date.fromisoformat(request.form["datum"]).isoformat(),
                 schicht, request.form.get("bewohner_id") or None, text,
                 1 if request.form.get("wichtig") else 0, g.benutzer["id"]),
            )
            g.db.commit()
            flash("Übergabe gespeichert.", "ok")
        except (ValueError, KeyError, sqlite3.Error) as e:
            g.db.rollback()
            flash(f"Nicht gespeichert: {e}", "fehler")
        return redirect(url_for("uebergaben", datum=request.form.get("datum", "")))

    try:
        tag = datetime.date.fromisoformat(request.args["datum"])
    except (ValueError, KeyError):
        tag = datetime.date.today()

    eintraege = g.db.execute(
        """SELECT u.*, b.name AS bewohner, b.zimmer, v.anzeigename AS verfasser
           FROM uebergaben u
           LEFT JOIN bewohner b ON b.id = u.bewohner_id
           JOIN benutzer v ON v.id = u.verfasser_id
           WHERE u.datum = ? ORDER BY u.wichtig DESC, u.id DESC""",
        (tag.isoformat(),),
    ).fetchall()

    nach_schicht = {s: [] for s in SCHICHTEN}
    for e in eintraege:
        nach_schicht.setdefault(e["schicht"], []).append(e)

    return render_template(
        "uebergaben.html",
        tag=tag.isoformat(),
        tag_name=WOCHENTAGE[tag.weekday()],
        vortag=(tag - datetime.timedelta(days=1)).isoformat(),
        folgetag=(tag + datetime.timedelta(days=1)).isoformat(),
        heute=datetime.date.today().isoformat(),
        schichten=SCHICHTEN,
        nach_schicht=nach_schicht,
        anzahl=len(eintraege),
        bewohner=g.db.execute(
            "SELECT * FROM bewohner WHERE aktiv = 1 ORDER BY zimmer, name").fetchall(),
    )


@app.route("/uebergabe/<int:eintrag_id>/loeschen", methods=["POST"])
@anmeldung_erforderlich
def uebergabe_loeschen(eintrag_id: int):
    eintrag = g.db.execute(
        "SELECT * FROM uebergaben WHERE id = ?", (eintrag_id,)).fetchone()
    if not eintrag:
        abort(404)
    # Nur die eigene Übergabe oder die Leitung darf löschen.
    if eintrag["verfasser_id"] != g.benutzer["id"] and g.benutzer["rolle"] != "leitung":
        flash("Nur der Verfasser oder die Leitung kann diesen Eintrag löschen.", "fehler")
        return redirect(url_for("uebergaben", datum=eintrag["datum"]))
    g.db.execute("DELETE FROM uebergaben WHERE id = ?", (eintrag_id,))
    g.db.commit()
    flash("Eintrag gelöscht.", "ok")
    return redirect(url_for("uebergaben", datum=eintrag["datum"]))


# ---------------------------------------------------------------- Verwaltung

@app.route("/bewohner", methods=["GET", "POST"])
@anmeldung_erforderlich
def bewohner_verwalten():
    if request.method == "POST":
        try:
            aktion = request.form.get("aktion")
            if aktion == "neu":
                name = request.form["name"].strip()
                if not name:
                    raise ValueError("Bitte einen Namen angeben.")
                g.db.execute(
                    """INSERT INTO bewohner (name, zimmer, wohnbereich, hinweis)
                       VALUES (?, ?, ?, ?)""",
                    (name, request.form.get("zimmer", "").strip(),
                     request.form.get("wohnbereich", "").strip(),
                     request.form.get("hinweis", "").strip()),
                )
                flash("Eintrag angelegt.", "ok")
            elif aktion == "ausziehen":
                # Nicht löschen, nur auf inaktiv setzen – Termine bleiben lesbar.
                g.db.execute("UPDATE bewohner SET aktiv = 0 WHERE id = ?",
                             (request.form["id"],))
                flash("Als ausgezogen markiert.", "ok")
            g.db.commit()
        except (ValueError, KeyError, sqlite3.Error) as e:
            g.db.rollback()
            flash(f"Nicht gespeichert: {e}", "fehler")
        return redirect(url_for("bewohner_verwalten"))

    return render_template(
        "bewohner.html",
        bewohner=g.db.execute(
            "SELECT * FROM bewohner WHERE aktiv = 1 ORDER BY zimmer, name").fetchall(),
    )


@app.route("/team", methods=["GET", "POST"])
@leitung_erforderlich
def team():
    if request.method == "POST":
        try:
            aktion = request.form.get("aktion")
            if aktion == "neu":
                benutzername = request.form["benutzername"].strip().lower()
                anzeigename = request.form.get("anzeigename", "").strip() or benutzername
                if not benutzername.isalnum():
                    raise ValueError("Der Benutzername darf nur Buchstaben und Zahlen enthalten.")
                start = request.form.get("startpasswort", "").strip() or "start-2026"
                if len(start) < 8:
                    raise ValueError("Das Startpasswort braucht mindestens 8 Zeichen.")
                g.db.execute(
                    """INSERT INTO benutzer (benutzername, anzeigename, passwort_hash, rolle)
                       VALUES (?, ?, ?, ?)""",
                    (benutzername, anzeigename, generate_password_hash(start),
                     "leitung" if request.form.get("rolle") == "leitung" else "pflege"),
                )
                flash(f"Zugang für {anzeigename} angelegt. Startpasswort: {start}", "ok")
            elif aktion == "sperren":
                if int(request.form["id"]) == g.benutzer["id"]:
                    raise ValueError("Der eigene Zugang kann nicht gesperrt werden.")
                g.db.execute("UPDATE benutzer SET aktiv = 0 WHERE id = ?",
                             (request.form["id"],))
                flash("Zugang gesperrt.", "ok")
            elif aktion == "zuruecksetzen":
                start = request.form.get("startpasswort", "").strip() or "start-2026"
                if len(start) < 8:
                    raise ValueError("Das Startpasswort braucht mindestens 8 Zeichen.")
                g.db.execute(
                    "UPDATE benutzer SET passwort_hash = ?, passwort_neu = 1 WHERE id = ?",
                    (generate_password_hash(start), request.form["id"]),
                )
                flash(f"Passwort zurückgesetzt auf: {start}", "ok")
            g.db.commit()
        except sqlite3.IntegrityError:
            g.db.rollback()
            flash("Diesen Benutzernamen gibt es schon.", "fehler")
        except (ValueError, KeyError, sqlite3.Error) as e:
            g.db.rollback()
            flash(f"Nicht gespeichert: {e}", "fehler")
        return redirect(url_for("team"))

    return render_template(
        "team.html",
        mitglieder=g.db.execute(
            "SELECT * FROM benutzer WHERE aktiv = 1 ORDER BY rolle, anzeigename").fetchall(),
    )


@app.route("/sw.js")
def service_worker():
    antwort = send_from_directory(app.static_folder, "sw.js")
    antwort.headers["Content-Type"] = "application/javascript; charset=utf-8"
    antwort.headers["Cache-Control"] = "no-cache"
    return antwort


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5001)), debug=False)
