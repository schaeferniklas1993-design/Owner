/* Auge-Knopf neben Passwortfeldern: blendet das eingegebene Passwort ein
   oder aus. Rein im Browser – das Passwort verlässt die Seite dabei nicht. */
(function () {
  "use strict";
  for (const knopf of document.querySelectorAll(".pw-auge")) {
    knopf.addEventListener("click", () => {
      const feld = knopf.parentElement.querySelector("input");
      if (!feld) return;
      const sichtbar = feld.type === "text";
      feld.type = sichtbar ? "password" : "text";
      knopf.textContent = sichtbar ? "👁" : "🙈";
      knopf.setAttribute("aria-pressed", String(!sichtbar));
      const text = sichtbar ? "Passwort anzeigen" : "Passwort verbergen";
      knopf.setAttribute("aria-label", text);
      knopf.title = text;
      // Schreibmarke ans Ende setzen, damit man direkt weitertippen kann.
      feld.focus();
      const ende = feld.value.length;
      feld.setSelectionRange(ende, ende);
    });
  }
})();
