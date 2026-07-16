/* Koppelt das Kategorie-Dropdown an die gewählte Art (Einnahme/Ausgabe):
   passende Optionen und Gruppen (optgroup) einblenden, andere ausblenden.
   Beim ersten Laden wird eine bereits gewählte Kategorie beibehalten. */
(function () {
  "use strict";
  const art = document.getElementById("art-auswahl");
  const kat = document.getElementById("kategorie-auswahl");
  if (!art || !kat) return;

  function anpassen(auswahlSetzen) {
    let erste = null;
    for (const gruppe of kat.querySelectorAll("optgroup")) {
      const passt = gruppe.dataset.gruppe === art.value;
      gruppe.hidden = !passt;
      gruppe.disabled = !passt;
      for (const option of gruppe.children) {
        option.hidden = !passt;
        option.disabled = !passt;
        if (passt && erste === null) erste = option;
      }
    }
    // Nur wenn die aktuelle Auswahl nicht mehr passt, auf die erste gültige springen.
    if (auswahlSetzen && kat.selectedOptions[0]?.disabled && erste) erste.selected = true;
  }

  art.addEventListener("change", () => anpassen(true));
  anpassen(false); // beim Laden: nur aus-/einblenden, gespeicherte Kategorie behalten
})();
