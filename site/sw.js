// L'appli hors ligne : la carte s'ouvre sans réseau en forêt, avec les données du dernier passage
// en ligne. Seuls les fichiers du site sont gardés (ni les fonds IGN, ni GitHub, ni ntfy) ;
// vider les données du site efface tout (déclaré dans a-propos.html).
//
// - le site et les données du jour (data/, pages) : le réseau d'abord, la copie s'il manque
//   (au-delà de 5 s, la copie, pour ne pas attendre un réseau qui traîne en forêt) ;
// - l'habitat (habitat/) : la copie d'abord, il ne change qu'avec une reconstruction.
//   Changer le format des blocs (france.FORMAT) = incrémenter VERSION, sinon les copies restent.
const VERSION = "champi-hors-ligne-1";
const COQUILLE = ["./", "index.html", "carte.js", "coins.js", "modele.js", "style.css", "favicon.svg",
  "vendor/leaflet/leaflet.js", "vendor/leaflet/leaflet.css", "manifest.webmanifest", "icone-192.png",
  "avant-de-partir.html", "a-propos.html"];
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
