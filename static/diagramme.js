/* Diagramme des Dashboards: Balkendiagramm (6 Monate) und Ringdiagramm (Kategorien).
   Reines SVG ohne externe Bibliotheken, mit Tooltip und Legende. */
(function () {
  "use strict";

  const dunkel = window.matchMedia("(prefers-color-scheme: dark)");

  // Kategoriale Palette in fester Reihenfolge (hell/dunkel je Modus).
  const PALETTE_HELL = ["#2a78d6", "#1baf7a", "#eda100", "#008300", "#4a3aa7", "#e34948", "#e87ba4", "#eb6834"];
  const PALETTE_DUNKEL = ["#3987e5", "#199e70", "#c98500", "#008300", "#9085e9", "#e66767", "#d55181", "#d95926"];

  function farben() {
    const stil = getComputedStyle(document.documentElement);
    return {
      einnahme: stil.getPropertyValue("--akzent").trim(),
      ausgabe: stil.getPropertyValue("--akzent-rot").trim(),
      gitter: stil.getPropertyValue("--linie").trim(),
      achse: stil.getPropertyValue("--tinte-3").trim(),
      flaeche: stil.getPropertyValue("--karte").trim(),
      palette: dunkel.matches ? PALETTE_DUNKEL : PALETTE_HELL,
    };
  }

  const euro = (wert) =>
    wert.toLocaleString("de-DE", { style: "currency", currency: "EUR" });

  // --- Tooltip -------------------------------------------------------------
  const tooltip = document.getElementById("tooltip");
  function tooltipZeigen(ereignis, titel, zeilen) {
    tooltip.innerHTML =
      `<div class="t-titel">${titel}</div>` +
      zeilen.map((z) => `<div class="t-zeile">${z}</div>`).join("");
    tooltip.hidden = false;
    const abstand = 14;
    let x = ereignis.clientX + abstand;
    let y = ereignis.clientY + abstand;
    const kasten = tooltip.getBoundingClientRect();
    if (x + kasten.width > window.innerWidth - 8) x = ereignis.clientX - kasten.width - abstand;
    if (y + kasten.height > window.innerHeight - 8) y = ereignis.clientY - kasten.height - abstand;
    tooltip.style.left = x + "px";
    tooltip.style.top = y + "px";
  }
  function tooltipVerstecken() { tooltip.hidden = true; }

  function el(name, attribute) {
    const knoten = document.createElementNS("http://www.w3.org/2000/svg", name);
    for (const [k, v] of Object.entries(attribute)) knoten.setAttribute(k, v);
    return knoten;
  }

  function legende(ziel, eintraege) {
    const div = document.createElement("div");
    div.className = "legende";
    for (const { name, farbe } of eintraege) {
      const eintrag = document.createElement("span");
      eintrag.className = "legende-eintrag";
      const punkt = document.createElement("span");
      punkt.className = "legende-punkt";
      punkt.style.background = farbe;
      eintrag.append(punkt, document.createTextNode(name));
      div.append(eintrag);
    }
    ziel.append(div);
  }

  // --- Balkendiagramm: Einnahmen vs. Ausgaben, letzte 6 Monate -------------
  function balkenZeichnen() {
    const ziel = document.getElementById("balken-diagramm");
    if (!ziel || !window.VERLAUF) return;
    ziel.innerHTML = "";
    const f = farben();
    const daten = window.VERLAUF;

    const breite = 520, hoehe = 240;
    const rand = { oben: 12, rechts: 8, unten: 26, links: 56 };
    const innenB = breite - rand.links - rand.rechts;
    const innenH = hoehe - rand.oben - rand.unten;

    // Obergrenze auf einen "runden" Wert anheben, damit die Achse saubere Schritte zeigt.
    const roh = Math.max(1, ...daten.flatMap((d) => [d.einnahme, d.ausgabe]));
    const zehner = Math.pow(10, Math.floor(Math.log10(roh)));
    const maxWert = [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]
      .map((f) => f * zehner).find((w) => w >= roh);

    const svg = el("svg", { viewBox: `0 0 ${breite} ${hoehe}`, width: "100%", role: "img",
                            "aria-label": "Einnahmen und Ausgaben der letzten sechs Monate" });

    // Gitterlinien und Y-Beschriftung (dezent).
    const schritte = 4;
    for (let i = 0; i <= schritte; i++) {
      const wert = (maxWert / schritte) * i;
      const y = rand.oben + innenH - (innenH * i) / schritte;
      svg.append(el("line", { x1: rand.links, x2: breite - rand.rechts, y1: y, y2: y,
                              stroke: f.gitter, "stroke-width": 1 }));
      const text = el("text", { x: rand.links - 8, y: y + 4, "text-anchor": "end",
                                fill: f.achse, "font-size": 11 });
      text.textContent = wert >= 1000
        ? (wert / 1000).toLocaleString("de-DE", { maximumFractionDigits: 1 }) + " T€"
        : Math.round(wert) + " €";
      svg.append(text);
    }

    const gruppenBreite = innenB / daten.length;
    const balkenBreite = Math.min(26, gruppenBreite / 2 - 6);
    daten.forEach((d, i) => {
      const mitte = rand.links + gruppenBreite * (i + 0.5);
      const serien = [
        { name: "Einnahmen", wert: d.einnahme, farbe: f.einnahme, x: mitte - balkenBreite - 1 },
        { name: "Ausgaben", wert: d.ausgabe, farbe: f.ausgabe, x: mitte + 1 },
      ];
      for (const s of serien) {
        const h = Math.max(s.wert > 0 ? 2 : 0, (innenH * s.wert) / maxWert);
        const y = rand.oben + innenH - h;
        // Balken mit oben abgerundeten Ecken, unten an der Basislinie verankert.
        const r = Math.min(4, h);
        const pfad = `M ${s.x} ${y + h} V ${y + r} Q ${s.x} ${y} ${s.x + r} ${y}` +
          ` H ${s.x + balkenBreite - r} Q ${s.x + balkenBreite} ${y} ${s.x + balkenBreite} ${y + r}` +
          ` V ${y + h} Z`;
        const balken = el("path", { d: pfad, fill: s.farbe });
        // Größere Trefferfläche für den Tooltip.
        const treffer = el("rect", { x: s.x - 3, y: rand.oben, width: balkenBreite + 6,
                                     height: innenH, fill: "transparent" });
        const zeigen = (ev) => tooltipZeigen(ev, d.label, [`${s.name}: ${euro(s.wert)}`,
          `Saldo: ${euro(d.einnahme - d.ausgabe)}`]);
        treffer.addEventListener("mousemove", zeigen);
        treffer.addEventListener("mouseleave", tooltipVerstecken);
        svg.append(balken, treffer);
      }
      const text = el("text", { x: mitte, y: hoehe - 8, "text-anchor": "middle",
                                fill: f.achse, "font-size": 11 });
      text.textContent = d.label;
      svg.append(text);
    });

    // Basislinie.
    svg.append(el("line", { x1: rand.links, x2: breite - rand.rechts,
                            y1: rand.oben + innenH, y2: rand.oben + innenH,
                            stroke: f.achse, "stroke-width": 1 }));

    ziel.append(svg);
    legende(ziel, [
      { name: "Einnahmen", farbe: f.einnahme },
      { name: "Ausgaben", farbe: f.ausgabe },
    ]);
  }

  // --- Ringdiagramm: Ausgaben nach Kategorie -------------------------------
  function ringZeichnen() {
    const ziel = document.getElementById("ring-diagramm");
    if (!ziel || !window.KATEGORIEN || !window.KATEGORIEN.length) return;
    ziel.innerHTML = "";
    const f = farben();

    // Höchstens 7 Kategorien einzeln, der Rest wird zu „Übrige“ zusammengefasst.
    let daten = window.KATEGORIEN.slice();
    if (daten.length > 8) {
      const rest = daten.slice(7).reduce((s, d) => s + d.wert, 0);
      daten = daten.slice(0, 7).concat([{ name: "Übrige", wert: rest }]);
    }
    const gesamt = daten.reduce((s, d) => s + d.wert, 0);

    const groesse = 240, mitte = groesse / 2, radius = 92, dicke = 34;
    const svg = el("svg", { viewBox: `0 0 ${groesse} ${groesse}`, width: "100%",
                            style: "max-width:260px;display:block;margin:0 auto",
                            role: "img", "aria-label": "Ausgaben nach Kategorie" });

    let winkel = -Math.PI / 2;
    daten.forEach((d, i) => {
      const anteil = d.wert / gesamt;
      const start = winkel;
      const ende = winkel + anteil * Math.PI * 2;
      winkel = ende;
      const gross = ende - start > Math.PI ? 1 : 0;
      const x1 = mitte + radius * Math.cos(start), y1 = mitte + radius * Math.sin(start);
      const x2 = mitte + radius * Math.cos(ende), y2 = mitte + radius * Math.sin(ende);
      const segment = el("path", {
        d: `M ${x1} ${y1} A ${radius} ${radius} 0 ${gross} 1 ${x2} ${y2}`,
        fill: "none",
        stroke: f.palette[i % f.palette.length],
        "stroke-width": dicke,
        // 2px Lücke zwischen den Segmenten über die Kartenfläche.
        "stroke-dasharray": `${Math.max(0.01, (ende - start) * radius - 2)} 1000`,
      });
      const zeigen = (ev) => tooltipZeigen(ev, d.name,
        [`${euro(d.wert)} · ${(anteil * 100).toFixed(1).replace(".", ",")} %`]);
      segment.addEventListener("mousemove", zeigen);
      segment.addEventListener("mouseleave", tooltipVerstecken);
      svg.append(segment);
    });

    const summe = el("text", { x: mitte, y: mitte - 2, "text-anchor": "middle",
                               fill: "currentColor", "font-size": 20, "font-weight": 700 });
    summe.textContent = euro(gesamt);
    const untertitel = el("text", { x: mitte, y: mitte + 18, "text-anchor": "middle",
                                    fill: f.achse, "font-size": 11 });
    untertitel.textContent = "Ausgaben gesamt";
    svg.append(summe, untertitel);

    ziel.append(svg);
    legende(ziel, daten.map((d, i) => ({
      name: `${d.name} (${euro(d.wert)})`,
      farbe: f.palette[i % f.palette.length],
    })));
  }

  function allesZeichnen() { balkenZeichnen(); ringZeichnen(); }
  allesZeichnen();
  dunkel.addEventListener("change", allesZeichnen);
})();
