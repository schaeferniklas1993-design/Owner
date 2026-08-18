/* Service Worker – macht das Haushaltsbuch auf Android als App installierbar.
 *
 * Bewusst "Netzwerk zuerst": Es wird IMMER erst der Server gefragt, der Cache
 * dient nur als Notnagel bei fehlender Verbindung. So kann eine neue Version
 * nie von alten zwischengespeicherten Dateien verdeckt werden.
 */
const CACHE = "haushaltsbuch-v1";

self.addEventListener("install", (e) => {
  self.skipWaiting(); // neue Fassung sofort übernehmen, nicht erst beim nächsten Start
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((namen) => Promise.all(
        namen.filter((n) => n !== CACHE).map((n) => caches.delete(n))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const anfrage = e.request;

  // Nur einfache Abrufe behandeln. Buchungen, Anmeldungen usw. (POST) und
  // fremde Adressen laufen unangetastet ans Netz.
  if (anfrage.method !== "GET" || !anfrage.url.startsWith(self.location.origin)) return;

  e.respondWith(
    fetch(anfrage)
      .then((antwort) => {
        // Erfolgreiche Antworten für den Offline-Fall beiseitelegen.
        if (antwort.ok) {
          const kopie = antwort.clone();
          caches.open(CACHE).then((c) => c.put(anfrage, kopie)).catch(() => {});
        }
        return antwort;
      })
      .catch(() => caches.match(anfrage).then(
        (treffer) => treffer || new Response(
          "<h1>Keine Verbindung</h1><p>Das Haushaltsbuch ist gerade nicht erreichbar.</p>",
          { status: 503, headers: { "Content-Type": "text/html; charset=utf-8" } }
        )
      ))
  );
});
