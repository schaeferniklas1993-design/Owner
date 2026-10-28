/* Verlaufsdiagramm: Soll- und Ist-Linie nebeneinander.
   Reines SVG, keine fremden Bibliotheken. */
(function () {
  "use strict";
  const daten = window.VERLAUF || [];
  const bereich = document.getElementById("diagramm-bereich");
  if (!bereich || !daten.length) return;

  const stil = getComputedStyle(document.documentElement);
  const farbe = (name, ersatz) =>
    (stil.getPropertyValue(name) || ersatz).trim();
  const sollFarbe = farbe("--soll", "#7c6bd4");
  const istFarbe = farbe("--ist", "#1f9d76");
  const linie = farbe("--linie", "#dfeae5");
  const tinte3 = farbe("--tinte-3", "#8aa096");

  const B = 760, H = 300;
  const rand = { oben: 18, rechts: 16, unten: 34, links: 54 };
  const innenB = B - rand.links - rand.rechts;
  const innenH = H - rand.oben - rand.unten;

  const werte = daten.flatMap(d => [d.soll, d.ist]).filter(v => v !== null);
  if (!werte.length) {
    bereich.innerHTML = '<p class="leer-hinweis">Sobald Plan und Einträge da sind, ' +
      'erscheint hier dein Verlauf.</p>';
    return;
  }
  const max = Math.max(...werte);
  // Obergrenze auf einen runden Wert anheben.
  const stufe = Math.pow(10, Math.floor(Math.log10(max || 1)));
  const maxY = [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]
    .map(f => f * stufe).find(w => w >= max) || max;

  const x = i => rand.links + (daten.length === 1 ? innenB / 2
                 : (innenB * i) / (daten.length - 1));
  const y = v => rand.oben + innenH - (innenH * v) / maxY;

  const ns = "http://www.w3.org/2000/svg";
  const el = (name, attr) => {
    const k = document.createElementNS(ns, name);
    for (const [a, w] of Object.entries(attr)) k.setAttribute(a, w);
    return k;
  };

  const svg = el("svg", {
    viewBox: `0 0 ${B} ${H}`, class: "diagramm", role: "img",
    "aria-label": "Verlauf von Soll- und Ist-Dosis"
  });

  // Hilfslinien und Beschriftung
  for (let i = 0; i <= 4; i++) {
    const wert = (maxY / 4) * i;
    const yy = y(wert);
    svg.append(el("line", {
      x1: rand.links, x2: B - rand.rechts, y1: yy, y2: yy,
      stroke: linie, "stroke-width": 1
    }));
    const t = el("text", {
      x: rand.links - 8, y: yy + 4, "text-anchor": "end",
      fill: tinte3, "font-size": 11
    });
    t.textContent = Math.round(wert);
    svg.append(t);
  }

  // Eine Linie zeichnen – Lücken (null) unterbrechen sie sauber.
  function linieZeichnen(feld, farbeLinie, gestrichelt) {
    let pfad = "", offen = false;
    daten.forEach((d, i) => {
      const v = d[feld];
      if (v === null || v === undefined) { offen = false; return; }
      pfad += (offen ? " L " : " M ") + x(i) + " " + y(v);
      offen = true;
    });
    if (!pfad) return;
    const attr = {
      d: pfad.trim(), fill: "none", stroke: farbeLinie,
      "stroke-width": 2.5, "stroke-linejoin": "round", "stroke-linecap": "round"
    };
    if (gestrichelt) attr["stroke-dasharray"] = "6 4";
    svg.append(el("path", attr));
  }

  linieZeichnen("soll", sollFarbe, true);
  linieZeichnen("ist", istFarbe, false);

  // Punkte auf der Ist-Linie
  daten.forEach((d, i) => {
    if (d.ist === null || d.ist === undefined) return;
    svg.append(el("circle", {
      cx: x(i), cy: y(d.ist), r: d.heute ? 5 : 3,
      fill: istFarbe, stroke: farbe("--karte", "#fff"), "stroke-width": 1.5
    }));
  });

  // Rückfalltage: kleine Markierung auf der Grundlinie. So sieht man auf
  // einen Blick, ob sie mit Ausschlägen bei der Dosis zusammenfallen.
  const warm = farbe("--warm", "#e8871e");
  const grundlinie = rand.oben + innenH;
  daten.forEach((d, i) => {
    if (!d.konsum) return;
    svg.append(el("line", {
      x1: x(i), x2: x(i), y1: rand.oben, y2: grundlinie,
      stroke: warm, "stroke-width": 1, opacity: 0.35
    }));
    svg.append(el("path", {
      d: `M ${x(i)} ${grundlinie - 7} L ${x(i) - 5} ${grundlinie + 2}` +
         ` L ${x(i) + 5} ${grundlinie + 2} Z`,
      fill: warm
    }));
  });

  // Datumsbeschriftung: nur einige, damit nichts überlappt.
  const schritt = Math.max(1, Math.round(daten.length / 7));
  daten.forEach((d, i) => {
    if (i % schritt !== 0 && i !== daten.length - 1) return;
    const t = el("text", {
      x: x(i), y: H - 12, "text-anchor": "middle", fill: tinte3, "font-size": 10
    });
    t.textContent = d.kurz;
    svg.append(t);
  });

  // Grundlinie
  svg.append(el("line", {
    x1: rand.links, x2: B - rand.rechts,
    y1: rand.oben + innenH, y2: rand.oben + innenH,
    stroke: tinte3, "stroke-width": 1
  }));

  bereich.innerHTML = "";
  bereich.append(svg);
})();
