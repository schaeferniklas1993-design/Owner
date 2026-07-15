"""Haushaltsbuch – Web-Oberfläche (Flask).

Start:  python3 app.py   →  http://localhost:5000
Zwei Zugänge: niklas / maeuschen (Startpasswörter siehe README).
"""
import csv
import datetime
import functools
import io
import os
import secrets

from flask import (Flask, Response, abort, flash, g, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import database
from database import cent, euro

MONATSNAMEN = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
               "August", "September", "Oktober", "November", "Dezember"]

KATEGORIE_ICONS = {
    # Einnahmen
    "Gehalt": "💼", "Nebeneinkünfte": "🪙", "Bonus & Prämie": "🏆",
    "Verkauf": "🏷️", "Zinsen & Kapitalerträge": "📈", "Kindergeld": "👶",
    "Rückerstattung": "💸", "Geschenk": "🎁", "Sonstige Einnahme": "✨",
    # Ausgaben
    "Miete": "🏠", "Nebenkosten": "💡", "Handy & Internet": "📱",
    "Lebensmittel": "🛒", "Versicherungen": "🛡️", "Kredite & Raten": "💳",
    "Mobilität": "🚗", "Gesundheit": "💊", "Kleidung": "👕",
    "Freizeit": "⚽", "Restaurant & Café": "🍽️", "Abos & Medien": "📺",
    "Haushalt": "🧺", "Möbel & Technik": "🛋️", "Urlaub & Reisen": "✈️",
    "Kinder": "🧸", "Haustiere": "🐾", "Geschenke": "🎁", "Bildung": "🎓",
    "Spenden": "❤️", "Steuern & Gebühren": "🧾", "Sparen & Rücklagen": "🏦",
    "Sonstige Ausgabe": "📦",
}


def datum_de(iso: str) -> str:
    """ISO-Datum als deutsche Schreibweise: 2026-07-07 -> 07.07.2026."""
    jahr, monat, tag = iso[:10].split("-")
    return f"{tag}.{monat}.{jahr}"


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

app.jinja_env.globals["csrf_token"] = lambda: session.get("csrf_token", "")
app.jinja_env.globals["kicon"] = lambda name: KATEGORIE_ICONS.get(name, "•")
app.jinja_env.filters["datum_de"] = datum_de


def _client_ip() -> str:
    """Adresse des Aufrufers; hinter Caddy steht sie in X-Forwarded-For."""
    weitergeleitet = request.headers.get("X-Forwarded-For", "")
    if weitergeleitet:
        return weitergeleitet.split(",")[0].strip()
    return request.remote_addr or "unbekannt"


@app.before_request
def vorbereiten():
    g.db = database.verbinden()
    database.dauerauftraege_ausfuehren(g.db)
    g.benutzer = None
    if session.get("benutzer_id"):
        g.benutzer = g.db.execute(
            "SELECT * FROM benutzer WHERE id = ?", (session["benutzer_id"],)
        ).fetchone()

    # CSRF-Schutz: Jedes POST-Formular muss das Token der eigenen Sitzung mitschicken,
    # damit fremde Webseiten keine Aktionen im Namen eines angemeldeten Benutzers auslösen.
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    if request.method == "POST":
        if not secrets.compare_digest(
            request.form.get("csrf_token", ""), session["csrf_token"]
        ):
            abort(400, "Ungültiges oder fehlendes Sicherheits-Token. Bitte Seite neu laden.")


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
        # Erster Login: Zuerst ein eigenes Passwort wählen, dann geht es weiter.
        if g.benutzer["muss_passwort_aendern"] and request.endpoint != "passwort_aendern":
            return redirect(url_for("passwort_aendern"))
        return view(*args, **kwargs)
    return wrapper


MAX_FEHLVERSUCHE = 5  # ... pro Minute, je Benutzername oder IP-Adresse


@app.route("/login", methods=["GET", "POST"])
def login():
    fehler = None
    if request.method == "POST":
        benutzername = request.form.get("benutzername", "").strip().lower()
        ip = _client_ip()

        # Login-Bremse: Alte Einträge wegräumen, dann Fehlversuche der letzten Minute zählen.
        g.db.execute("DELETE FROM login_versuche WHERE zeit < datetime('now', '-1 hour')")
        fehlversuche = g.db.execute(
            "SELECT COUNT(*) AS n FROM login_versuche"
            " WHERE zeit > datetime('now', '-60 seconds') AND (benutzername = ? OR ip = ?)",
            (benutzername, ip),
        ).fetchone()["n"]
        if fehlversuche >= MAX_FEHLVERSUCHE:
            g.db.commit()
            return render_template(
                "login.html",
                fehler="Zu viele Fehlversuche. Bitte eine Minute warten und erneut versuchen.",
            ), 429

        zeile = g.db.execute(
            "SELECT * FROM benutzer WHERE benutzername = ?", (benutzername,)
        ).fetchone()
        if zeile and check_password_hash(zeile["passwort_hash"], request.form.get("passwort", "")):
            g.db.execute("DELETE FROM login_versuche WHERE benutzername = ?", (benutzername,))
            g.db.commit()
            session.clear()
            session["benutzer_id"] = zeile["id"]
            session["csrf_token"] = secrets.token_hex(16)
            return redirect(url_for("dashboard"))

        g.db.execute(
            "INSERT INTO login_versuche (benutzername, ip) VALUES (?, ?)", (benutzername, ip)
        )
        g.db.commit()
        fehler = "Benutzername oder Passwort ist falsch."
    return render_template("login.html", fehler=fehler)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/passwort", methods=["GET", "POST"])
@anmeldung_erforderlich
def passwort_aendern():
    erzwungen = bool(g.benutzer["muss_passwort_aendern"])
    if request.method == "POST":
        fehler = None
        neu = request.form.get("neues_passwort", "")
        # Beim erzwungenen ersten Wechsel wurde das aktuelle Passwort gerade
        # erst beim Login eingegeben; bei freiwilligem Wechsel fragen wir es ab.
        if not erzwungen and not check_password_hash(
            g.benutzer["passwort_hash"], request.form.get("aktuelles_passwort", "")
        ):
            fehler = "Das aktuelle Passwort ist falsch."
        elif len(neu) < 8:
            fehler = "Das neue Passwort muss mindestens 8 Zeichen haben."
        elif neu != request.form.get("wiederholung", ""):
            fehler = "Die beiden Eingaben stimmen nicht überein."
        elif neu.lower() in (g.benutzer["benutzername"], f"{g.benutzer['benutzername']}-start"):
            fehler = "Bitte ein eigenes, neues Passwort wählen."

        if fehler:
            flash(fehler, "fehler")
        else:
            g.db.execute(
                "UPDATE benutzer SET passwort_hash = ?, muss_passwort_aendern = 0 WHERE id = ?",
                (generate_password_hash(neu), g.benutzer["id"]),
            )
            g.db.commit()
            flash("Dein neues Passwort ist gespeichert. Ab jetzt meldest du dich damit an.", "ok")
            return redirect(url_for("dashboard"))
    return render_template("passwort.html", erzwungen=erzwungen)


@app.route("/konto", methods=["GET", "POST"])
@anmeldung_erforderlich
def konto():
    """Kontostand direkt setzen, ohne eine Buchung anzulegen.

    Die Differenz wird als Startsaldo gespeichert – alle Buchungen bleiben unverändert.
    """
    def buchungssumme(benutzer_id: int) -> int:
        return g.db.execute(
            "SELECT COALESCE(SUM(CASE WHEN art = 'einnahme' THEN betrag_cent"
            " ELSE -betrag_cent END), 0) AS s FROM buchungen WHERE benutzer_id = ?",
            (benutzer_id,),
        ).fetchone()["s"]

    if request.method == "POST":
        try:
            gewuenscht = database.cent_signed(request.form["kontostand"])
            g.db.execute(
                "UPDATE benutzer SET startsaldo_cent = ? WHERE id = ?",
                (gewuenscht - buchungssumme(g.benutzer["id"]), g.benutzer["id"]),
            )
            g.db.commit()
            flash(f"Dein Kontostand wurde auf {euro(gewuenscht)} gesetzt.", "ok")
            return redirect(url_for("dashboard"))
        except (ValueError, KeyError):
            flash("Bitte einen gültigen Betrag eingeben, z. B. 843,20 oder -120,50.", "fehler")
        return redirect(url_for("konto"))

    personen = [
        {"name": u["anzeigename"],
         "kontostand": u["startsaldo_cent"] + buchungssumme(u["id"]),
         "eigene": u["id"] == g.benutzer["id"]}
        for u in g.db.execute("SELECT * FROM benutzer ORDER BY id")
    ]
    return render_template("konto.html", personen=personen)


def _sparziel_stand(sparziel_id: int) -> int:
    return g.db.execute(
        "SELECT COALESCE(SUM(betrag_cent), 0) AS s FROM spar_bewegungen WHERE sparziel_id = ?",
        (sparziel_id,),
    ).fetchone()["s"]


@app.route("/sparen", methods=["GET", "POST"])
@anmeldung_erforderlich
def sparen():
    """Gemeinsame Sparziele (Sparkonto) für Urlaub, Haus & Co."""
    if request.method == "POST":
        aktion = request.form.get("aktion")
        try:
            if aktion == "neu":
                name = request.form["name"].strip()
                if not name:
                    raise ValueError("Bitte einen Namen angeben.")
                ziel = database.cent_signed(request.form.get("zielbetrag") or "0")
                g.db.execute(
                    "INSERT INTO sparziele (name, icon, zielbetrag_cent) VALUES (?, ?, ?)",
                    (name, (request.form.get("icon") or "🎯").strip()[:4], max(0, ziel)),
                )
                flash("Sparziel angelegt.", "ok")
            elif aktion in ("einzahlen", "entnehmen"):
                betrag = database.cent(request.form["betrag"])
                if aktion == "entnehmen":
                    betrag = -betrag
                g.db.execute(
                    "INSERT INTO spar_bewegungen (sparziel_id, benutzer_id, betrag_cent,"
                    " beschreibung, datum) VALUES (?, ?, ?, ?, ?)",
                    (request.form["id"], g.benutzer["id"], betrag,
                     request.form.get("beschreibung", "").strip(),
                     datetime.date.today().isoformat()),
                )
                flash("Einzahlung gespeichert." if betrag > 0 else "Entnahme gespeichert.", "ok")
            elif aktion == "ziel":
                g.db.execute(
                    "UPDATE sparziele SET zielbetrag_cent = ? WHERE id = ?",
                    (max(0, database.cent_signed(request.form.get("zielbetrag") or "0")),
                     request.form["id"]),
                )
                flash("Zielbetrag aktualisiert.", "ok")
            elif aktion == "loeschen":
                g.db.execute("DELETE FROM spar_bewegungen WHERE sparziel_id = ?", (request.form["id"],))
                g.db.execute("DELETE FROM sparziele WHERE id = ?", (request.form["id"],))
                flash("Sparziel gelöscht.", "ok")
            g.db.commit()
        except (ValueError, KeyError) as e:
            flash(f"Nicht gespeichert: {e}", "fehler")
        return redirect(url_for("sparen"))

    ziele = []
    gesamt = 0
    for z in g.db.execute("SELECT * FROM sparziele WHERE aktiv = 1 ORDER BY id"):
        stand = _sparziel_stand(z["id"])
        gesamt += stand
        prozent = round(stand / z["zielbetrag_cent"] * 100) if z["zielbetrag_cent"] else None
        letzte = g.db.execute(
            """SELECT b.*, u.anzeigename AS person FROM spar_bewegungen b
               JOIN benutzer u ON u.id = b.benutzer_id
               WHERE b.sparziel_id = ? ORDER BY b.datum DESC, b.id DESC LIMIT 5""",
            (z["id"],),
        ).fetchall()
        ziele.append({
            "id": z["id"], "name": z["name"], "icon": z["icon"],
            "ziel": z["zielbetrag_cent"], "stand": stand,
            "prozent": prozent, "rest": max(0, z["zielbetrag_cent"] - stand),
            "letzte": letzte,
        })
    return render_template("sparen.html", ziele=ziele, gesamt=gesamt)


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
    # Alle Benutzer anzeigen, auch ohne Buchungen im Monat – inklusive Kontostand
    # (Startsaldo + alle Buchungen bis zum Ende des angezeigten Monats).
    naechster_key = _monat_verschieben(jahr, monat, 1)
    for u in g.db.execute(
        "SELECT id, anzeigename, benutzername, startsaldo_cent FROM benutzer ORDER BY id"
    ):
        person = pro_person.setdefault(
            u["id"], {"name": u["anzeigename"], "einnahme": 0, "ausgabe": 0}
        )
        gesamt = g.db.execute(
            "SELECT COALESCE(SUM(CASE WHEN art = 'einnahme' THEN betrag_cent"
            " ELSE -betrag_cent END), 0) AS s FROM buchungen"
            " WHERE benutzer_id = ? AND datum < ?",
            (u["id"], f"{naechster_key}-01"),
        ).fetchone()["s"]
        person["kontostand"] = u["startsaldo_cent"] + gesamt
        person["benutzername"] = u["benutzername"]

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

    # Vergleich mit dem Vormonat für die Kacheln.
    vormonat_summen = {"einnahme": 0, "ausgabe": 0}
    for zeile in g.db.execute(
        "SELECT art, SUM(betrag_cent) AS summe FROM buchungen"
        " WHERE strftime('%Y-%m', datum) = ? GROUP BY art",
        (_monat_verschieben(jahr, monat, -1),),
    ):
        vormonat_summen[zeile["art"]] = zeile["summe"]
    vergleich = {
        "einnahme": summen["einnahme"] - vormonat_summen["einnahme"],
        "ausgabe": summen["ausgabe"] - vormonat_summen["ausgabe"],
        "saldo": (summen["einnahme"] - summen["ausgabe"])
        - (vormonat_summen["einnahme"] - vormonat_summen["ausgabe"]),
    }

    # Ausgaben nach Kategorie für das Ringdiagramm.
    kategorien_summen = [
        {"name": f"{KATEGORIE_ICONS.get(zeile['name'], '•')} {zeile['name']}",
         "wert": zeile["summe"] / 100}
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
        vergleich=vergleich,
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

    # CSV-Export der aktuellen Auswahl, z. B. für Excel oder die Steuer.
    if request.args.get("export") == "csv":
        puffer = io.StringIO()
        schreiber = csv.writer(puffer, delimiter=";")
        schreiber.writerow(["Datum", "Person", "Art", "Kategorie", "Beschreibung", "Betrag in Euro"])
        for b in zeilen:
            betrag = b["betrag_cent"] / 100
            if b["art"] == "ausgabe":
                betrag = -betrag
            schreiber.writerow([
                datum_de(b["datum"]), b["person"],
                "Einnahme" if b["art"] == "einnahme" else "Ausgabe",
                b["kategorie"], b["beschreibung"],
                f"{betrag:.2f}".replace(".", ","),
            ])
        # BOM voranstellen, damit Excel die Umlaute korrekt erkennt.
        antwort = Response("\ufeff" + puffer.getvalue(), mimetype="text/csv; charset=utf-8")
        antwort.headers["Content-Disposition"] = (
            f"attachment; filename=haushaltsbuch-{monat_key}.csv"
        )
        return antwort

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
