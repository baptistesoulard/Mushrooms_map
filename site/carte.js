// Carte de l'indice de pousse, France entière.
// Vue large (zoom < DETAIL) : l'aperçu national calculé chaque matin (pixels de 1,15 km).
// Vue rapprochée : le navigateur calcule lui-même l'indice des cases de 50 m, bloc par bloc
// (habitat/blocs/*.png, data/meteo/*.bin, modele.js), à la résolution de calcul.
import { installerCoins } from "./coins.js";
import { evaluer, indices, preparer } from "./modele.js";

const R = 6378137;
const MONDE = 2 * Math.PI * R;
const DETAIL = 11;                     // à partir de ce zoom, une case ≈ un pixel d'écran
const CLE_ESPECE = "champi-espece";    // gardées dans le navigateur (voir a-propos.html)
const CLE_DEPARTEMENT = "champi-departement";
const NIVEAU_COURT = ["hors saison", "défavorable", "possible", "par endroits", "bon"];
const OPACITE = 175;                   // sur 255 : le fond de carte reste lisible
const PROTEGE = 252;                   // code d'une case protégée (hachures)
const CENTRES_ANTIPOISON = [           // centres-antipoison.net, vérifié le 2026-10-31
  ["Angers", 47.47, -0.55, "02 41 48 21 21"], ["Bordeaux", 44.84, -0.58, "05 56 96 40 80"],
  ["Lille", 50.63, 3.06, "08 00 59 59 59"], ["Lyon", 45.76, 4.84, "04 72 11 69 11"],
  ["Marseille", 43.30, 5.37, "04 91 75 25 25"], ["Nancy", 48.69, 6.18, "03 83 22 50 50"],
  ["Paris", 48.86, 2.35, "01 40 05 48 48"], ["Toulouse", 43.60, 1.44, "05 61 77 74 47"],
];

const fr = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 });
const fr2 = new Intl.NumberFormat("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fr1 = new Intl.NumberFormat("fr-FR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

const $ = (id) => document.getElementById(id);
const el = (tag, attrs = {}, ...enfants) => {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") n.className = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v);
  }
  for (const e of enfants) n.append(e);
  return n;
};

function versMerc(lat, lon) {
  return [R * lon * Math.PI / 180, R * Math.log(Math.tan(Math.PI / 4 + lat * Math.PI / 360))];
}
function latDeY(y) {
  return (2 * Math.atan(Math.exp(y / R)) - Math.PI / 2) * 180 / Math.PI;
}

function lire(cle) {
  try { return localStorage.getItem(cle); } catch { return null; }
}
function ecrire(cle, v) {
  try { localStorage.setItem(cle, v); } catch { /* navigation privée : sans conséquence */ }
}

// Décode un PNG en octets RVBA bruts : sans conversion de couleur ni prémultiplication (ce
// sont des données, pas une image), et hors du fil principal.
async function pixels(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url} : ${r.status}`);
  const bmp = await createImageBitmap(await r.blob(), { colorSpaceConversion: "none", premultiplyAlpha: "none" });
  const c = document.createElement("canvas");
  c.width = bmp.width;
  c.height = bmp.height;
  const ctx = c.getContext("2d", { willReadFrequently: true });
  ctx.drawImage(bmp, 0, 0);
  bmp.close();
  return { l: c.width, h: c.height, d: ctx.getImageData(0, 0, c.width, c.height).data };
}

// Mémoire bornée : les plus anciennes entrées partent d'abord.
function memoire(taille, charger) {
  const m = new Map();
  return (cle) => {
    if (m.has(cle)) {
      const v = m.get(cle);
      m.delete(cle);
      m.set(cle, v);
      return v;
    }
    const p = charger(cle).catch((e) => { m.delete(cle); throw e; });
    m.set(cle, p);
    if (m.size > taille) m.delete(m.keys().next().value);
    return p;
  };
}

function couleurs() {
  const s = getComputedStyle(document.documentElement);
  const hex = (v) => {
    const h = s.getPropertyValue(v).trim().replace("#", "");
    return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
  };
  return { classes: [null, hex("--classe-1"), hex("--classe-2"), hex("--classe-3"), hex("--classe-4")],
           hachure: hex("--hachure") };
}

function classeDe(v, classes) {
  for (let k = 0; k < classes.length; k++) if (v < classes[k].seuil) return k;
  return classes.length - 1;
}

async function demarrer() {
  const [carte, regles] = await Promise.all([
    fetch("data/carte.json").then((r) => r.json()),
    fetch("data/especes.json").then((r) => r.json()),
  ]);
  const especes = Object.fromEntries(regles.especes.map((e) => [e.code, e]));
  const communs = regles.communs;
  const deps = Object.fromEntries(carte.departements.map((d) => [d.code, d]));
  const B = carte.blocs;
  const blocsPresents = new Set(B.liste);
  const leg = carte.legendes;
  const pal = couleurs();

  // Couleur de chaque code d'indice (0-255), calculée une fois : RVBA à plat.
  const TABLE = new Uint8ClampedArray(256 * 4);
  for (let code = 0; code <= carte.echelle; code++) {
    const k = classeDe(code / carte.echelle, carte.classes);
    if (k > 0) TABLE.set([...pal.classes[k], OPACITE], code * 4);
  }

  // --- Jour de référence et fraîcheur -------------------------------------------
  const aujourdhui = new Date().toLocaleDateString("sv-SE", { timeZone: "Europe/Paris" });
  let jourDepart = carte.jours.findIndex((j) => j.date === aujourdhui);
  if (jourDepart < 0) jourDepart = 0;
  if (carte.jours[0].date < aujourdhui) {
    const p = $("perime");
    p.hidden = false;
    p.textContent = `Cette carte a été calculée le ${dateLongue(carte.jours[0].date)} : la mise à jour ` +
      "quotidienne n'a pas eu lieu. Les jours proposés commencent donc avant aujourd'hui.";
  }
  const jourDe = (k) => {
    const [a, m, j] = carte.jours[k].date.split("-").map(Number);
    return { annee: a, num: Date.UTC(a, m - 1, j) / 864e5, k };
  };

  // --- Données à la demande --------------------------------------------------------
  const resumes = memoire(8, (dep) => fetch(`data/resumes/${dep}.json`).then((r) => r.json()));
  const apercus = memoire(6, async (cle) => {
    const px = await pixels(`data/apercu/${cle}.png`);
    const v = new Uint8Array(px.l * px.h);
    for (let i = 0; i < v.length; i++) v[i] = px.d[i * 4];
    return v;
  });
  const annexes = memoire(2, (nom) => fetch(nom).then((r) => r.json()));   // communes, zones protégées

  // Habitat d'un bloc : les cases boisées, à plat, plus ce qu'il faut pour dessiner.
  const habitats = memoire(40, async (nom) => {
    const [a, b, c] = await Promise.all(["a", "b", "c"].map((l) => pixels(`habitat/blocs/${nom}_${l}.png`)));
    const [bx, by] = nom.split("_").map(Number);
    const n = B.taille * B.taille;
    const essence = new Uint8Array(n), protege = new Uint8Array(n), commune = new Uint16Array(n);
    const foret = [];
    for (let i = 0; i < n; i++) {
      const q = i * 4;
      essence[i] = a.d[q + 2] & 15;
      protege[i] = c.d[q + 2];
      commune[i] = (c.d[q] << 8) | c.d[q + 1];
      if (essence[i] > 0) foret.push(i);
    }
    const nf = foret.length;
    const cases = {
      lat: new Float64Array(nf), lon: new Float64Array(nf), altitude: new Float64Array(nf),
      ensoleillement: new Float64Array(nf), pente: new Float64Array(nf), essence: new Uint8Array(nf),
      ouverte: new Uint8Array(nf), public: new Uint8Array(nf), roche: new Uint8Array(nf), orientation: new Uint8Array(nf),
    };
    const y1 = (by + 1) * B.cote, x0 = bx * B.cote;
    foret.forEach((i, f) => {
      const q = i * 4, lig = Math.floor(i / B.taille), col = i % B.taille;
      cases.lat[f] = latDeY(y1 - (lig + 0.5) * B.pas);
      cases.lon[f] = (x0 + (col + 0.5) * B.pas) / R * 180 / Math.PI;
      cases.altitude[f] = ((a.d[q] << 8) | a.d[q + 1]) - B.altitude_decalage;
      cases.essence[f] = essence[i];
      cases.ouverte[f] = (a.d[q + 2] >> 4) & 1;
      cases.public[f] = (a.d[q + 2] >> 5) & 1;
      cases.pente[f] = b.d[q];
      cases.ensoleillement[f] = (b.d[q + 1] - 100) / 100;
      cases.roche[f] = b.d[q + 2] & 3;
      cases.orientation[f] = b.d[q + 2] >> 2;
    });
    return { nom, essence, protege, commune, foret: Int32Array.from(foret), cases, prep: null };
  });

  const meteos = memoire(40, async (nom) => {
    const v = new Int16Array(await fetch(`data/meteo/${nom}.bin`).then((r) => r.arrayBuffer()));
    const [ni, nj, i0, j0] = v;
    const n = ni * nj, M = carte.meteo;
    const champs = {};
    M.champs.forEach((c, k) => {
      const f = new Float32Array(n);
      for (let i = 0; i < n; i++) f[i] = v[4 + k * n + i] / 10;
      champs[c] = f;
    });
    const arrondi = (x) => Math.round(x * 1e4) / 1e4;
    return {
      lats: Array.from({ length: ni }, (_, i) => arrondi(M.lat0 + (i0 + i) * M.pas)),
      lons: Array.from({ length: nj }, (_, j) => arrondi(M.lon0 + (j0 + j) * M.pas)),
      champ: (c) => champs[c],
    };
  });

  // Codes d'un bloc pour l'espèce et le jour : un octet par case, comme l'aperçu.
  const codesBlocs = memoire(60, async (cle) => {
    const [nom, esp, k] = cle.split("|");
    const [h, m] = await Promise.all([habitats(nom), meteos(nom)]);
    if (!h.prep) h.prep = preparer(h.cases, m);
    const ind = indices(especes[esp], h.prep, m, jourDe(Number(k)), communs);
    const codes = new Uint8Array(B.taille * B.taille);
    h.foret.forEach((i, f) => {
      codes[i] = h.protege[i] ? PROTEGE : Math.min(carte.echelle, Math.round(ind[f] * carte.echelle));
    });
    return codes;
  });

  // --- État ---------------------------------------------------------------------
  const memoDep = lire(CLE_DEPARTEMENT);
  const etat = {
    departement: deps[memoDep]?.centre ? memoDep : "74",
    espece: especes[lire(CLE_ESPECE)] ? lire(CLE_ESPECE) : carte.especes[0].code,
    jour: jourDepart,
  };

  // --- Carte ----------------------------------------------------------------------
  const ba = carte.apercu.bornes;
  const france = L.latLngBounds([ba.sud, ba.ouest], [ba.nord, ba.est]);
  const map = L.map("carte", { minZoom: 5, maxZoom: 18, maxBounds: france.pad(0.2), zoomSnap: 0.5 });
  const d0 = deps[etat.departement];
  const vueInitiale = () => map.fitBounds(d0?.bornes ? [[d0.bornes[0], d0.bornes[1]], [d0.bornes[2], d0.bornes[3]]] : france);
  vueInitiale();
  // Un conteneur encore sans taille (onglet en arrière-plan, mise en page tardive) : la vue
  // se recale dès qu'il en prend une.
  let vueFaite = map.getSize().x > 0;
  new ResizeObserver(() => {
    map.invalidateSize();
    if (!vueFaite && map.getSize().x > 0) { vueFaite = true; vueInitiale(); }
  }).observe($("carte"));
  map.attributionControl.setPrefix(false);
  const wmts = (couche, format) =>
    "https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&STYLE=normal" +
    `&TILEMATRIXSET=PM&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&LAYER=${couche}&FORMAT=${format}`;
  const fonds = {
    plan: L.tileLayer(wmts("GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2", "image/png"),
      { maxZoom: 19, attribution: "Fond © IGN" }),
    photo: L.tileLayer(wmts("ORTHOIMAGERY.ORTHOPHOTOS", "image/jpeg"),
      { maxZoom: 19, attribution: "Photographies © IGN" }),
  };
  fonds.plan.addTo(map);
  map.attributionControl.addAttribution("Indice : météo Météo-France et ECMWF via Open-Meteo, forêts et relief IGN, roches BRGM");

  const ControleFonds = L.Control.extend({
    onAdd() {
      const div = L.DomUtil.create("div", "fonds");
      L.DomEvent.disableClickPropagation(div);
      for (const [cle, nom] of [["plan", "Plan"], ["photo", "Photos"]]) {
        const bt = el("button", { type: "button", "aria-pressed": String(cle === "plan") }, nom);
        bt.addEventListener("click", () => {
          for (const f of Object.values(fonds)) map.removeLayer(f);
          fonds[cle].addTo(map).bringToBack();
          div.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === bt)));
        });
        div.append(bt);
      }
      return div;
    },
  });
  new ControleFonds({ position: "topright" }).addTo(map);

  // Position Mercator du centre de chaque pixel d'une tuile.
  function axes(coords) {
    const n = 256 * 2 ** coords.z;
    const xs = new Float64Array(256), ys = new Float64Array(256);
    for (let i = 0; i < 256; i++) {
      xs[i] = ((coords.x * 256 + i + 0.5) / n) * MONDE - MONDE / 2;
      ys[i] = MONDE / 2 - ((coords.y * 256 + i + 0.5) / n) * MONDE;
    }
    return { xs, ys };
  }

  function peindre(o, p, code, hachure) {
    if (code === PROTEGE) {             // hachures : « réglementation propre », jamais un gris plein
      if (hachure) { o[p] = pal.hachure[0]; o[p + 1] = pal.hachure[1]; o[p + 2] = pal.hachure[2]; o[p + 3] = 150; }
      return;
    }
    const t = code * 4;
    o[p] = TABLE[t]; o[p + 1] = TABLE[t + 1]; o[p + 2] = TABLE[t + 2]; o[p + 3] = TABLE[t + 3];
  }

  // Vue large : l'aperçu national.
  const g = carte.apercu.grille;
  let apercu = null;
  const Apercu = L.GridLayer.extend({
    createTile(coords) {
      const tuile = document.createElement("canvas");
      tuile.width = tuile.height = 256;
      if (!apercu) return tuile;
      const { xs, ys } = axes(coords);
      const ctx = tuile.getContext("2d");
      const img = ctx.createImageData(256, 256);
      for (let j = 0; j < 256; j++) {
        const lig = Math.floor((g.y1 - ys[j]) / g.pas);
        if (lig < 0 || lig >= g.ny) continue;
        for (let i = 0; i < 256; i++) {
          const col = Math.floor((xs[i] - g.x0) / g.pas);
          if (col < 0 || col >= g.nx) continue;
          const code = apercu[lig * g.nx + col];
          if (code <= carte.echelle) peindre(img.data, (j * 256 + i) * 4, code, false);
        }
      }
      ctx.putImageData(img, 0, 0);
      return tuile;
    },
  });
  const calqueApercu = new Apercu({ pane: "overlayPane", maxZoom: DETAIL - 0.5, updateWhenZooming: false }).addTo(map);

  // Vue rapprochée : chaque tuile réunit les blocs qu'elle touche, calculés à la demande.
  const Detail = L.GridLayer.extend({
    createTile(coords, fini) {
      const tuile = document.createElement("canvas");
      tuile.width = tuile.height = 256;
      const { xs, ys } = axes(coords);
      const cle = `${etat.espece}|${etat.jour}`;
      const noms = new Set();
      for (const x of [xs[0], xs[255]]) for (const y of [ys[0], ys[255]]) {
        const nom = `${Math.floor(x / B.cote)}_${Math.floor(y / B.cote)}`;
        if (blocsPresents.has(nom)) noms.add(nom);
      }
      if (!noms.size) { setTimeout(() => fini(null, tuile)); return tuile; }
      Promise.all([...noms].map((nom) => codesBlocs(`${nom}|${cle}`).then((c) => [nom, c])))
        .then((liste) => {
          const blocs = new Map(liste);
          const ctx = tuile.getContext("2d");
          const img = ctx.createImageData(256, 256);
          for (let j = 0; j < 256; j++) {
            const by = Math.floor(ys[j] / B.cote);
            const lig = Math.floor(((by + 1) * B.cote - ys[j]) / B.pas);
            for (let i = 0; i < 256; i++) {
              const bx = Math.floor(xs[i] / B.cote);
              const codes = blocs.get(`${bx}_${by}`);
              if (!codes) continue;
              const col = Math.floor((xs[i] - bx * B.cote) / B.pas);
              const code = codes[lig * B.taille + col];
              if (code === 0) continue;
              peindre(img.data, (j * 256 + i) * 4, code, (coords.x * 256 + i + coords.y * 256 + j) % 7 < 2);
            }
          }
          ctx.putImageData(img, 0, 0);
          fini(null, tuile);
        })
        .catch((e) => { console.error(e); fini(null, tuile); });
      return tuile;
    },
  });
  const calqueDetail = new Detail({ pane: "overlayPane", minZoom: DETAIL, updateWhenZooming: false, keepBuffer: 1 }).addTo(map);

  // Indice d'un coin noté par l'utilisateur, pour le jour affiché : moyenne des cases boisées
  // à moins de 75 m (3 × 3 cases), tirée des mêmes codes que la carte.
  async function indiceEn(lat, lon, code) {
    const [x, y] = versMerc(lat, lon);
    const bx = Math.floor(x / B.cote), by = Math.floor(y / B.cote);
    const nom = `${bx}_${by}`;
    if (!blocsPresents.has(nom)) return null;
    const [h, codes, communes] = await Promise.all([
      habitats(nom), codesBlocs(`${nom}|${code}|${etat.jour}`), annexes("habitat/communes.json")]);
    const col = Math.floor((x - bx * B.cote) / B.pas), lig = Math.floor(((by + 1) * B.cote - y) / B.pas);
    let s = 0, n = 0, protege = false;
    for (let l = Math.max(0, lig - 1); l <= Math.min(B.taille - 1, lig + 1); l++) {
      for (let c = Math.max(0, col - 1); c <= Math.min(B.taille - 1, col + 1); c++) {
        const i = l * B.taille + c;
        if (h.protege[i]) protege = true;
        else if (h.essence[i] > 0) { s += codes[i] / carte.echelle; n++; }
      }
    }
    return { indice: n ? s / n : null, protege, commune: communes[h.commune[lig * B.taille + col] - 1]?.nom };
  }

  const coins = installerCoins({
    map, especes, ordre: carte.especes.map((e) => e.code),
    etat: () => ({ espece: etat.espece, libelle: carte.jours[etat.jour].libelle }),
    indiceEn,
    decrire: (v) => {
      const k = classeDe(v, carte.classes);
      return { nom: carte.classes[k].nom, couleur: k > 0 ? `rgb(${pal.classes[k].join(",")})` : null };
    },
  });

  // --- Ma position ------------------------------------------------------------------
  // Demandée à l'ouverture pour choisir le département, puis montrée et suivie tant que la
  // page est visible ; un bouton recentre ou arrête. Elle ne quitte jamais l'appareil.
  const calquePosition = L.layerGroup().addTo(map);
  let suivi = null, actif = false, derniere = null, aCentrer = false, depAuto = false, depOuverture = null;

  async function departementEn(lat, lon) {
    const [x, y] = versMerc(lat, lon);
    const bx = Math.floor(x / B.cote), by = Math.floor(y / B.cote);
    const nom = `${bx}_${by}`;
    if (!blocsPresents.has(nom)) return null;
    const [h, communes] = await Promise.all([habitats(nom), annexes("habitat/communes.json")]);
    const col = Math.floor((x - bx * B.cote) / B.pas), lig = Math.floor(((by + 1) * B.cote - y) / B.pas);
    const com = communes[h.commune[lig * B.taille + col] - 1];
    return com && deps[com.dep]?.centre ? com.dep : null;
  }

  function vue(pos) {
    const ll = L.latLng(pos.coords.latitude, pos.coords.longitude);
    const premiere = !derniere;
    derniere = ll;
    calquePosition.clearLayers();
    L.circle(ll, { radius: pos.coords.accuracy, interactive: false, color: "#1a73e8", weight: 1,
                   fillOpacity: 0.1 }).addTo(calquePosition);
    L.circleMarker(ll, { radius: 7, interactive: false, color: "#fff", weight: 3, fillColor: "#1a73e8",
                         fillOpacity: 1 }).addTo(calquePosition);
    if (aCentrer) { aCentrer = false; map.setView(ll, Math.max(map.getZoom(), 14)); }
    if (premiere) {
      departementEn(ll.lat, ll.lng).then((dep) => {
        // À l'ouverture, un département choisi entre-temps par l'utilisateur l'emporte.
        if (depAuto && etat.departement !== depOuverture) return;
        if (dep && dep !== etat.departement) allerDepartement(dep, depAuto);
      }).catch((err) => console.error(err));
    }
  }

  function erreurPosition(err) {
    arreter();
    if (depAuto) return;   // à l'ouverture, rien à dire : la carte garde le dernier département
    L.popup().setLatLng(map.getCenter()).setContent(err.code === err.PERMISSION_DENIED
      ? "Position refusée : le navigateur s'en souvient. Autorisez-la pour ce site dans ses " +
        "réglages (le cadenas à gauche de l'adresse, ou Réglages › Safari › Position sur iPhone)."
      : "Position introuvable pour l'instant. Réessayez à découvert.").openOn(map);
  }

  function suivre() {
    if (suivi === null) {
      suivi = navigator.geolocation.watchPosition(vue, erreurPosition,
        { enableHighAccuracy: true, timeout: 30000, maximumAge: 10000 });
    }
  }
  function pause() {
    if (suivi !== null) navigator.geolocation.clearWatch(suivi);
    suivi = null;
  }
  function arreter() {
    pause();
    actif = false;
    derniere = null;
    calquePosition.clearLayers();
    boutonPosition.classList.remove("actif");
  }
  function activer({ centrer, auto }) {
    actif = true;
    aCentrer = centrer;
    depAuto = auto;
    depOuverture = etat.departement;
    boutonPosition.classList.add("actif");
    suivre();
  }

  const boutonPosition = L.DomUtil.create("button", "bouton-position");
  boutonPosition.type = "button";
  boutonPosition.title = "Ma position";
  boutonPosition.setAttribute("aria-label", "Ma position");
  boutonPosition.innerHTML = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">' +
    '<circle cx="12" cy="12" r="4" fill="currentColor"/><circle cx="12" cy="12" r="8" fill="none" ' +
    'stroke="currentColor" stroke-width="2"/><path d="M12 1v4M12 19v4M1 12h4M19 12h4" stroke="currentColor" ' +
    'stroke-width="2"/></svg>';
  L.DomEvent.disableClickPropagation(boutonPosition);
  boutonPosition.addEventListener("click", () => {
    if (!navigator.geolocation) { erreurPosition({ code: 0 }); return; }
    if (!actif) { activer({ centrer: true, auto: false }); return; }
    // Déjà suivie : un appui recentre ; un appui quand la carte y est déjà centrée l'arrête.
    if (derniere && map.getCenter().distanceTo(derniere) > 30) map.setView(derniere, Math.max(map.getZoom(), 14));
    else arreter();
  });
  const Controle = L.Control.extend({
    onAdd() {
      const div = L.DomUtil.create("div", "leaflet-bar");
      div.append(boutonPosition);
      return div;
    },
  });
  new Controle({ position: "topleft" }).addTo(map);
  document.addEventListener("visibilitychange", () => {
    if (!actif) return;
    if (document.visibilityState === "visible") suivre(); else pause();
  });

  // À l'ouverture, la position est demandée (choix de l'utilisateur, 2026-10-31) pour se
  // placer d'emblée sur son département ; après un refus, plus rien : le navigateur s'en
  // souvient, et le bouton dit comment revenir dessus.
  async function positionOuverture() {
    if (!navigator.geolocation) return;
    try {
      if ((await navigator.permissions?.query({ name: "geolocation" }))?.state === "denied") return;
    } catch { /* sans l'API des permissions : on demande */ }
    activer({ centrer: false, auto: true });
  }

  async function rafraichirCalques() {
    const demande = `${etat.espece}_${etat.jour}`;
    const a = await apercus(demande);
    if (demande !== `${etat.espece}_${etat.jour}`) return;   // l'utilisateur a déjà changé d'avis
    apercu = a;
    calqueApercu.redraw();
    calqueDetail.redraw();
    if (etat.jour + 1 < carte.jours.length) apercus(`${etat.espece}_${etat.jour + 1}`).catch(() => {});
  }

  // --- Panneau --------------------------------------------------------------------
  let resume = null;    // résumés du département affiché, par espèce

  function choixDepartement() {
    const s = $("choix-departement");
    if (!s.options.length) {
      // Par numéro, la Corse (2A, 2B) à la place du 20.
      const cle = (code) => code.replace(/^2([AB])$/, "20$1");
      const tri = carte.departements.filter((d) => d.centre).sort((a, b) => cle(a.code).localeCompare(cle(b.code)));
      for (const d of tri) s.append(el("option", { value: d.code }, `${d.code} – ${d.nom}`));
      s.addEventListener("change", () => allerDepartement(s.value, true));
    }
    s.value = etat.departement;
  }

  async function allerDepartement(code, centrer) {
    etat.departement = code;
    ecrire(CLE_DEPARTEMENT, code);
    const d = deps[code];
    if (centrer && d.bornes) map.fitBounds([[d.bornes[0], d.bornes[1]], [d.bornes[2], d.bornes[3]]]);
    resume = await resumes(code);
    if (etat.departement === code) panneau();
  }

  function choixEspeces() {
    const zone = $("choix-espece");
    zone.replaceChildren();
    for (const e of carte.especes) {
      const r = resume?.[e.code]?.[etat.jour];
      const input = el("input", { type: "radio", name: "espece", value: e.code });
      input.checked = e.code === etat.espece;
      input.addEventListener("change", () => { etat.espece = e.code; ecrire(CLE_ESPECE, e.code); tout(); });
      zone.append(el("label", {}, input, e.nom, el("span", { class: "niv" }, r ? NIVEAU_COURT[r.niveau] : "")));
    }
  }

  function choixJours() {
    const zone = $("choix-jour");
    zone.replaceChildren();
    carte.jours.forEach((j, k) => {
      const input = el("input", { type: "radio", name: "jour", value: String(k) });
      input.checked = k === etat.jour;
      input.addEventListener("change", () => { etat.jour = k; tout(); });
      zone.append(el("label", { title: j.libelle }, input, jourCourt(j.date, aujourdhui)));
    });
  }

  function fiche() {
    const e = especes[etat.espece];
    const dep = deps[etat.departement];
    const lat = dep?.centre?.[0] ?? communs.latitude_ref;
    // Dates de la saison à la latitude du département (loi de Hopkins, comme le calcul).
    const date = (mmjj) => {
      const [m, j] = mmjj.split("-").map(Number);
      const sens = m <= 6 ? 1 : m >= 8 ? -1 : 0;
      const d = new Date(Date.UTC(2026, m - 1, j) + Math.round(sens * communs.hopkins_jours * (lat - communs.latitude_ref)) * 864e5);
      return dateCourte(`${d.getUTCMonth() + 1}-${d.getUTCDate()}`);
    };
    const corps = [
      el("p", {}, e.description),
      el("p", {}, el("strong", {}, dep ? `Saison (${dep.nom}) : ` : "Saison : "),
        `surtout du ${date(e.saison[1])} au ${date(e.saison[2])}. `, el("strong", {}, "Milieu : "), e.habitat_texte),
    ];
    if (e.repere) corps.push(el("p", {}, el("strong", {}, "Repère de terrain : "), e.repere));
    if (e.confusions) corps.push(el("p", { class: "confusions" }, el("strong", {}, "Confusions possibles : "), e.confusions));
    corps.push(el("p", { class: "muet" }, "Ce portrait ne suffit jamais pour identifier un champignon."));
    $("fiche").replaceChildren(
      el("details", { open: "" },
        el("summary", {}, el("strong", {}, e.nom), " ", el("span", { class: "latin" }, e.latin)),
        ...corps));
  }

  // La semaine du département : le niveau de chaque espèce, jour par jour (celui du verdict).
  // Un clic affiche l'espèce et le jour sur la carte.
  function semaine() {
    const tete = el("tr", {}, el("th", {}, ""), ...carte.jours.map((j, k) => {
      const d = new Date(`${j.date}T12:00:00`);
      return el("th", { scope: "col", title: j.libelle, class: k === etat.jour ? "actuel" : "" },
        d.toLocaleDateString("fr-FR", { weekday: "short" }), el("br"), String(d.getDate()));
    }));
    const lignes = carte.especes.map((e) => el("tr", {}, el("th", { scope: "row" }, e.nom),
      ...carte.jours.map((j, k) => {
        const r = resume?.[e.code]?.[k];
        const texte = `${e.nom}, ${j.libelle} : ${r ? r.verdict.toLowerCase() : "pas de forêt calculée"}`;
        const choisi = e.code === etat.espece && k === etat.jour;
        return el("td", {}, el("button", {
          type: "button", class: `niveau n${r ? r.niveau : "x"}${choisi ? " choisi" : ""}`,
          title: texte, "aria-label": texte,
          onclick: () => { etat.espece = e.code; etat.jour = k; ecrire(CLE_ESPECE, e.code); tout(); },
        }, r?.niveau === 0 ? "–" : ""));
      })));
    $("semaine").replaceChildren(el("thead", {}, tete), el("tbody", {}, ...lignes));
  }

  function classement() {
    const ol = $("classement");
    ol.replaceChildren();
    const liste = carte.classement[etat.espece][etat.jour].filter((c) => c.indice >= 0.05).slice(0, 8);
    if (!liste.length) ol.append(el("li", { class: "muet" }, "Aucun département ne se détache ce jour-là."));
    for (const c of liste) {
      const k = classeDe(c.indice, carte.classes);
      ol.append(el("li", {}, el("button", { type: "button", onclick: () => allerDepartement(c.dep, true) },
        `${deps[c.dep]?.nom ?? c.dep} (${c.dep})`, el("span", { class: "cl" }, carte.classes[k].nom))));
    }
  }

  function verdict() {
    const e = especes[etat.espece];
    const d = deps[etat.departement];
    $("verdict-jour").textContent = `${e.nom}, ${carte.jours[etat.jour].libelle} — ${d?.nom ?? ""}`;
    const r = resume?.[etat.espece]?.[etat.jour];
    if (!r) {
      $("verdict-titre").textContent = "Pas de forêt calculée dans ce département.";
      $("verdict-texte").replaceChildren();
      $("tranches").replaceChildren();
      $("communes").replaceChildren();
      return;
    }
    $("verdict-titre").textContent = r.verdict;
    $("verdict-texte").replaceChildren(...r.phrases.map((p) => el("p", {}, p)));
    const f = (carte.fiabilite || {})[etat.espece];
    if (f) {
      $("verdict-texte").append(el("p", { class: `fiabilite ${f.sens}` }, `${f.texte} `,
        el("a", { href: "validation.html" }, "Détails")));
    }

    const tr = $("tranches");
    tr.replaceChildren();
    const max = Math.max(0.4, ...r.tranches.map((t) => t.indice));
    const best = r.meilleure_tranche;
    for (const t of r.tranches.slice().reverse()) {
      const estBest = best && t.de === best[0];
      tr.append(el("div", { class: "tranche" + (estBest ? " meilleure" : ""),
        title: `${fr.format(t.km2)} km² de forêt, sol à ${fr1.format(t.sol)} °C en moyenne` },
        `${fr.format(t.de)}–${fr.format(t.a)} m`,
        el("div", { class: "barre-fond" }, el("div", { class: "barre", style: `width:${(t.indice / max) * 100}%` })),
        el("span", { class: "val" }, fr2.format(t.indice))));
    }

    const ul = $("communes");
    ul.replaceChildren();
    if (!r.communes.length || r.niveau === 0) ul.append(el("li", { class: "muet" }, "Aucune commune ne se détache."));
    for (const c of r.niveau === 0 ? [] : r.communes) {
      ul.append(el("li", {}, el("button", { type: "button", onclick: () => allerA(c.centre) },
        c.nom, el("span", { class: "cl" }, carte.classes[c.classe].nom))));
    }
  }

  function allerA(centre) {
    map.setView(centre, 13);
    if (window.matchMedia("(max-width: 820px)").matches) $("carte").scrollIntoView({ behavior: "smooth" });
  }

  function legende() {
    const z = $("legende");
    z.replaceChildren();
    for (let k = carte.classes.length - 1; k >= 1; k--) {
      const c = pal.classes[k];
      const bas = carte.classes[k - 1].seuil;
      z.append(el("div", {}, el("span", { class: "pastille", style: `background:rgb(${c.join(",")})` }),
        `${carte.classes[k].nom} (${fr2.format(bas)} et plus)`));
    }
    z.append(el("div", {}, el("span", { class: "pastille hachure" }),
      "Zone protégée : réglementation propre, pas d'indice"));
    z.append(el("div", {}, el("span", { class: "pastille vide" }),
      "Sans couleur : indice très faible, ou hors forêt"));
    z.append(el("p", { class: "muet" }, `En vue large, chaque pixel résume environ 1 km² ; ` +
      "zoomez pour voir les cases de 50 m."));
  }

  function antipoison() {
    const c = map.getCenter();
    const [ville, , , tel] = CENTRES_ANTIPOISON.reduce((m, v) =>
      (Math.hypot(v[1] - c.lat, (v[2] - c.lng) * 0.7) < Math.hypot(m[1] - c.lat, (m[2] - c.lng) * 0.7) ? v : m));
    $("antipoison").textContent = `centre antipoison le plus proche (${ville}) : ${tel}`;
  }
  map.on("moveend", antipoison);

  // --- Fenêtre d'une case ---------------------------------------------------------
  map.on("click", async (ev) => {
    if (map.getZoom() < DETAIL) { map.setView(ev.latlng, DETAIL + 1); return; }
    const [x, y] = versMerc(ev.latlng.lat, ev.latlng.lng);
    const bx = Math.floor(x / B.cote), by = Math.floor(y / B.cote);
    const nom = `${bx}_${by}`;
    if (!blocsPresents.has(nom)) return;
    const col = Math.floor((x - bx * B.cote) / B.pas), lig = Math.floor(((by + 1) * B.cote - y) / B.pas);
    const i = lig * B.taille + col;
    const popup = L.popup({ maxWidth: 330 }).setLatLng(ev.latlng).setContent("Chargement…").openOn(map);
    try {
      const [h, m, communes, zones] = await Promise.all([
        habitats(nom), meteos(nom), annexes("habitat/communes.json"), annexes("habitat/blocs.json")]);
      popup.setContent(fenetre(h, m, i, communes, zones.blocs[nom], ev.latlng));
    } catch (err) {
      console.error(err);
      popup.setContent("Les détails de cette case n'ont pas pu se charger.");
    }
  });

  function fenetre(h, meteo, i, communes, infoBloc, ll) {
    const e = especes[etat.espece];
    const com = communes[h.commune[i] - 1];
    const div = el("div");
    if (!com) {
      div.append(el("p", {}, "Hors de France : pas d'indice."));
      return div;
    }
    div.append(el("h4", {}, `${com.nom} (${com.dep})`));
    if (h.protege[i]) {
      const z = infoBloc?.protections?.[h.protege[i] - 1];
      div.append(el("p", {}, `${z ? `${z.nature} « ${z.nom} »` : "Zone protégée"}. Ces espaces ont leur propre ` +
        "réglementation, souvent plus stricte sur la cueillette : renseignez-vous avant d'y ramasser quoi que ce soit. " +
        "Le site n'y calcule pas d'indice."));
      return div;
    }
    const f = h.foret.indexOf(i);
    if (f < 0) {
      div.append(el("p", {}, "Hors forêt : pas d'indice."), boutonCoin(ll));
      return div;
    }
    const k = h.cases;
    const cas = { essence: k.essence[f], ouverte: k.ouverte[f], roche: k.roche[f], altitude: k.altitude[f],
                  pente: k.pente[f], ensoleillement: k.ensoleillement[f], lat: k.lat[f], lon: k.lon[f] };
    const r = evaluer(e, cas, meteo, jourDe(etat.jour), communs);
    const kc = classeDe(r.indice, carte.classes);
    const pastille = kc > 0 ? el("span", { class: "pastille", style: `background:rgb(${pal.classes[kc].join(",")})` })
      : el("span", { class: "pastille vide" });
    div.append(el("div", { class: "pop-indice" }, pastille,
      `${e.nom} : ${carte.classes[kc].nom.toLowerCase()} (${fr2.format(r.indice)})`));
    div.append(el("div", { class: "muet" }, carte.jours[etat.jour].libelle));

    const [p0, p1] = e.pluie_mm;
    const [, s1, s2] = e.sol;
    const mot = (a) => (a >= 0.8 ? "élevée" : a >= 0.5 ? "moyenne" : "faible");
    const dl = el("dl");
    const ligne = (t, d, cls) => { dl.append(el("dt", {}, t), el("dd", cls ? { class: cls } : {}, d)); };
    ligne("Forêt", `${leg.essences[cas.essence]}${cas.ouverte ? " (ouverte)" : ""}`);
    ligne("Affinité", `${mot(e.essences[cas.essence] ?? 0)} pour cette forêt, ${mot(e.roches[cas.roche] ?? 0)} pour la roche`);
    ligne("Roche", leg.roches[cas.roche]);
    ligne("Altitude", `${fr.format(cas.altitude)} m`);
    ligne("Exposition", leg.orientations[k.orientation[f]]);
    ligne("Statut", k.public[f] ? "forêt publique (régime forestier)" : "forêt probablement privée");
    const [jmin, jmax] = e.pluie_jours;
    ligne(`Pluie ${jmin}–${jmax} j avant`,
      `${fr.format(r.pluie)} mm ${r.pluie >= p1 ? "✓" : r.pluie < p0 ? "✗ trop peu" : "– un peu juste"}`,
      r.pluie >= p1 ? "ok" : r.pluie < p0 ? "ko" : "");
    ligne("Sol (7 jours)", `${fr1.format(r.tSol)} °C ${r.tSol < s1 ? "✗ trop froid" : r.tSol > s2 ? "✗ trop chaud" : "✓"}`,
      r.tSol < s1 || r.tSol > s2 ? "ko" : "ok");
    if (r.gel) ligne("Gel", `${r.gel} jour${r.gel > 1 ? "s" : ""} sur 7`, "ko");
    if (r.saison < 1) ligne("Saison", r.saison === 0 ? "hors saison ✗" : "début ou fin de saison", r.saison === 0 ? "ko" : "");
    div.append(dl);
    div.append(el("p", { class: "muet" },
      `Case de 50 m ; météo AROME à 2,5 km. Pleine pousse au-delà de ${fr.format(p1)} mm, ` +
      `sol entre ${fr.format(s1)} et ${fr.format(s2)} °C.`));
    if (com.dep !== etat.departement && deps[com.dep]) {
      div.append(el("p", {}, el("button", { type: "button", class: "lien", onclick: () => allerDepartement(com.dep, false) },
        `Résumé du département : ${deps[com.dep].nom}`)));
    }
    div.append(el("a", {
      href: `https://www.geoportail.gouv.fr/carte?c=${ll.lng.toFixed(5)},${ll.lat.toFixed(5)}&z=16&permalink=yes`,
      target: "_blank", rel: "noopener",
    }, "Voir le lieu sur le Géoportail (IGN)"), " ", boutonCoin(ll));
    return div;
  }

  function boutonCoin(ll) {
    return el("button", { type: "button", class: "lien", onclick: () => coins.formulaire(ll) }, "Noter une trouvaille ici");
  }

  function panneau() {
    choixDepartement();
    choixEspeces();
    fiche();
    classement();
    verdict();
    semaine();
  }

  function tout() {
    choixJours();
    panneau();
    rafraichirCalques();
    coins.rafraichir();
  }

  legende();
  antipoison();
  resume = await resumes(etat.departement);
  if (!lire(CLE_ESPECE)) {   // première visite : l'espèce la mieux placée dans le département
    const meilleure = carte.especes.slice().sort((a, b) =>
      (resume[b.code]?.[jourDepart]?.niveau ?? 0) - (resume[a.code]?.[jourDepart]?.niveau ?? 0))[0];
    etat.espece = meilleure.code;
  }
  tout();
  positionOuverture();
  const genere = new Date(carte.genere_le);
  $("maj").textContent = `Calculée le ${genere.toLocaleString("fr-FR", { dateStyle: "long", timeStyle: "short", timeZone: "Europe/Paris" })}.`
    + (carte.blocs_manquants ? ` Habitat en cours de construction : ${carte.blocs_manquants} carrés de 25 km encore vides.` : "");
}

const MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
  "septembre", "octobre", "novembre", "décembre"];

function dateCourte(mmjj) {
  const [m, j] = mmjj.split("-").map(Number);
  return `${j === 1 ? "1er" : j} ${MOIS[m - 1]}`;
}

function dateLongue(iso) {
  return new Date(`${iso}T12:00:00`).toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" });
}

function jourCourt(iso, aujourdhui) {
  if (iso === aujourdhui) return "Aujourd'hui";
  const d = new Date(`${iso}T12:00:00`);
  const a = new Date(`${aujourdhui}T12:00:00`);
  if (Math.round((d - a) / 864e5) === 1) return "Demain";
  return d.toLocaleDateString("fr-FR", { weekday: "short", day: "numeric" });
}

demarrer().catch((err) => {
  console.error(err);
  $("verdict-titre").textContent = "La carte n'a pas pu se charger.";
});
