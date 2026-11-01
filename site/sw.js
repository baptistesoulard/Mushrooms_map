// L'appli hors ligne : la carte (carte/) s'ouvre sans réseau en forêt, avec les données du dernier
// passage en ligne. Seuls les fichiers du site sont gardés (ni les fonds IGN, ni GitHub) ; vider
// les données du site efface tout (déclaré dans a-propos.html).
//
// - le site et les données du jour (data/, pages) : le réseau d'abord, la copie s'il manque
//   (au-delà de 5 s, la copie, pour ne pas attendre un réseau qui traîne en forêt) ;
// - l'habitat (habitat/) : la copie d'abord, il ne change qu'avec une reconstruction.
//   Changer le format des blocs (france.FORMAT) = incrémenter VERSION, sinon les copies restent.
const VERSION = "champi-hors-ligne-1";
const COQUILLE = ["carte/", "./", "carte.js", "coins.js", "alertes.js", "modele.js", "partage.js", "itineraire.js", "pages.js", "style.css",
  "favicon.svg", "vendor/leaflet/leaflet.js", "vendor/leaflet/leaflet.css", "manifest.webmanifest",
  "icone-192.png", "avant-de-partir.html", "a-propos.html"];
const LIMITES = { coquille: 100, donnees: 400, habitat: 600 };   // entrées gardées par cache
const DELAI_MS = 5000;

self.addEventListener("install", (ev) => {
  ev.waitUntil(caches.open(`${VERSION}-coquille`).then((c) => c.addAll(COQUILLE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (ev) => {
  ev.waitUntil(caches.keys()
    .then((cles) => Promise.all(cles.filter((k) => !k.startsWith(`${VERSION}-`)).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

// Alertes (champi/alertes.py) : le contenu arrive chiffré, le navigateur le déchiffre et le montre.
self.addEventListener("push", (ev) => {
  let d = {};
  try { d = ev.data ? ev.data.json() : {}; } catch { d = { texte: ev.data?.text() || "" }; }
  ev.waitUntil(self.registration.showNotification(d.titre || "Champignons", {
    body: d.texte || "", icon: "icone-192.png", badge: "icone-192.png", tag: d.tag, data: { lien: d.lien },
  }));
});

// Un appui sur la notification ouvre la page qu'elle annonce, dans l'appli si elle est ouverte.
self.addEventListener("notificationclick", (ev) => {
  ev.notification.close();
  const lien = ev.notification.data?.lien || self.registration.scope;
  ev.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((fenetres) => {
    const ici = fenetres.find((f) => f.url.startsWith(self.registration.scope));
    return ici ? ici.navigate(lien).then((f) => f?.focus()) : self.clients.openWindow(lien);
  }));
});

self.addEventListener("fetch", (ev) => {
  const url = new URL(ev.request.url);
  if (ev.request.method !== "GET" || url.origin !== self.location.origin) return;   // le réseau seul
  const chemin = url.pathname.slice(new URL(self.registration.scope).pathname.length);
  if (chemin.startsWith("habitat/")) ev.respondWith(dabordCopie(ev.request, "habitat"));
  else ev.respondWith(dabordReseau(ev.request, chemin.startsWith("data/") ? "donnees" : "coquille"));
});

async function dabordReseau(requete, nom) {
  const cache = await caches.open(`${VERSION}-${nom}`);
  // Une page ouverte par un lien (?departement=85…) retombe sur la copie de la page nue.
  const copie = await cache.match(requete, { ignoreSearch: requete.mode === "navigate" });
  try {
    const reponse = await (copie ? avecDelai(fetch(requete), DELAI_MS) : fetch(requete));
    if (reponse.ok) garder(cache, nom, requete, reponse.clone());
    return reponse;
  } catch (err) {
    if (copie) return copie;
    throw err;
  }
}

async function dabordCopie(requete, nom) {
  const cache = await caches.open(`${VERSION}-${nom}`);
  const copie = await cache.match(requete);
  if (copie) return copie;
  const reponse = await fetch(requete);
  if (reponse.ok) garder(cache, nom, requete, reponse.clone());
  return reponse;
}

async function garder(cache, nom, requete, reponse) {
  await cache.put(requete, reponse);
  const cles = await cache.keys();                 // dans l'ordre d'arrivée : les plus anciennes d'abord
  for (const k of cles.slice(0, Math.max(0, cles.length - LIMITES[nom]))) await cache.delete(k);
}

function avecDelai(promesse, ms) {
  return Promise.race([promesse, new Promise((_, refus) => setTimeout(() => refus(new Error("délai")), ms))]);
}
