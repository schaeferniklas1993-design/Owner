/* Kleine Helfer für die Oberfläche:
   - Auge-Knopf blendet Passwörter ein und aus
   - Befinden- und Symptom-Schalter werden beim Antippen sichtbar markiert */
(function () {
  "use strict";

  // Passwort ein-/ausblenden
  for (const knopf of document.querySelectorAll(".pw-auge")) {
    knopf.addEventListener("click", () => {
      const feld = knopf.parentElement.querySelector("input");
      if (!feld) return;
      const sichtbar = feld.type === "text";
      feld.type = sichtbar ? "password" : "text";
      knopf.textContent = sichtbar ? "👁" : "🙈";
      knopf.setAttribute("aria-label", sichtbar ? "Passwort anzeigen" : "Passwort verbergen");
      feld.focus();
      feld.setSelectionRange(feld.value.length, feld.value.length);
    });
  }

  // Befinden: nur eine Auswahl gleichzeitig
  const befinden = document.querySelectorAll(".befinden-knopf");
  for (const knopf of befinden) {
    knopf.addEventListener("click", () => {
      befinden.forEach(k => k.classList.remove("gewaehlt"));
      knopf.classList.add("gewaehlt");
    });
  }

  // Symptome: mehrere möglich
  for (const schalter of document.querySelectorAll(".symptom")) {
    const kaestchen = schalter.querySelector("input");
    if (!kaestchen) continue;
    schalter.addEventListener("click", () => {
      // Der Klick schaltet das Kästchen selbst um; wir folgen nur optisch.
      setTimeout(() => schalter.classList.toggle("gewaehlt", kaestchen.checked), 0);
    });
  }
})();
