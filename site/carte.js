// Carte de l'indice de pousse, France entière.
// Vue large (zoom < DETAIL) : l'aperçu national calculé chaque matin (pixels de 1,15 km).
// Vue rapprochée : le navigateur calcule lui-même l'indice, bloc par bloc (data/meteo/*.bin,
// modele.js) : par zones de 250 m pour tout le monde (data/zones/*.png, champi/zones.py), par
// cases de 50 m avec le mot de passe de la carte fine (habitat/fin/, déchiffré par fin.js).
import { installerAlertes } from "./alertes.js";
import { installerCoins } from "./coins.js";
import { installerFeuille } from "./feuille.js";
import { cleGardee, dechiffrer, deriver, garder, importer, oublier } from "./fin.js";
import { installerGuide } from "./guide.js";
import { niveau as niveauZone, partsZone } from "./ici.js";
import { liensItineraire } from "./itineraire.js";
import { datesSaison, evaluer, facteurSaison, indices, preparer } from "./modele.js";
import { partager } from "./partage.js";

const R = 6378137;
const MONDE = 2 * Math.PI * R;
const DETAIL = 11;                     // à partir de ce zoom, une case ≈ un pixel d'écran
const SYNTHESE = 8;                    // en dessous, la vue France : le verdict par carrés de 9,2 km
const CARRES_FINS = 7;                 // … et dès ce zoom (jusqu'à SYNTHESE), par carrés de 4,6 km
const CONTOURS_JUSQUA = 11.5;          // les contours des départements, en dessous de ce zoom
const CLE_ESPECE = "champi-espece";    // gardées dans le navigateur (voir a-propos.html)
const CLE_DEPARTEMENT = "champi-departement";
const CLE_FOND = "champi-fond";
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
  return pixelsDe(await r.blob());
}

async function pixelsDe(blob) {
  const bmp = await createImageBitmap(blob, { colorSpaceConversion: "none", premultiplyAlpha: "none" });
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

// Une couleur par classe visible (--classe-1, --classe-2…), la première restant transparente.
function couleurs(n) {
  const s = getComputedStyle(document.documentElement);
  const hex = (v) => {
    const h = s.getPropertyValue(v).trim().replace("#", "");
    return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
  };
  return { classes: [null, ...Array.from({ length: n - 1 }, (_, k) => hex(`--classe-${k + 1}`))],
           hachure: hex("--hachure"), exploration: hex("--exploration") };
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
  // Une espèce des prés n'a pas de carte fine (les prés sont presque tous privés) : pas de
  // calque, un bandeau sur la carte le dit, et le panneau garde départements et communes.
  const desPres = (code) => especes[code]?.milieu === "pre";
  const communs = regles.communs;
  const deps = Object.fromEntries(carte.departements.map((d) => [d.code, d]));
  const B = carte.blocs;
  const blocsPresents = new Set(B.liste);
  // La carte publique, par zones de 250 m (carte.zones) ; la carte fine, par cases de 50 m, pour
  // qui a la clé (carte.fine : ses couches sont chiffrées). Sans carte.zones (un essai sur le
  // poste, habitat en clair), la carte fine est la seule.
  const Z = carte.zones;
  let cleFine = await cleGardee(carte.fine);
  const modeFin = () => !Z || cleFine !== null;
  const leg = carte.legendes;
  const pal = couleurs(carte.classes.length);

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
  const octets = async (chemin) => {
    const px = await pixels(chemin);
    const v = new Uint8Array(px.l * px.h);
    for (let i = 0; i < v.length; i++) v[i] = px.d[i * 4];
    return v;
  };
  const vues = memoire(3, (k) => octets(`data/vue/${k}.png`));
  const vuesFines = memoire(3, (k) => octets(`data/vue_fine/${k}.png`));
  const apercus = memoire(6, async (cle) => {
    const px = await pixels(`data/apercu/${cle}.png`);
    const v = new Uint8Array(px.l * px.h);
    for (let i = 0; i < v.length; i++) v[i] = px.d[i * 4];
    return v;
  });
  const annexes = memoire(2, (nom) => fetch(nom).then((r) => r.json()));   // communes, zones protégées

  // Habitat d'un bloc : les cases boisées, à plat, plus ce qu'il faut pour dessiner. La couche
  // « d » (champi.sol) : bits 0-6 = pH du sol × 10, bit 7 = zone urbanisée, dont les bois ne
  // comptent pas comme forêt. Une release ancienne peut ne pas l'avoir : rien n'est alors exclu.
  // Une couche d'un bloc : chiffrée (a, b, d de la carte fine) ou en clair (c, ou un essai sur le poste).
  async function couche(nom, l) {
    if (!carte.fine || l === "c") return pixels(`habitat/blocs/${nom}_${l}.png`);
    if (!cleFine) throw new Error("carte fine verrouillée");
    const url = `habitat/fin/${carte.fine.id}/${nom}_${l}.bin`;
    const r = await fetch(url);
    if (!r.ok) throw new Error(`${url} : ${r.status}`);
    const png = await dechiffrer(cleFine, `${nom}_${l}.png`, await r.arrayBuffer());
    return pixelsDe(new Blob([png], { type: "image/png" }));
  }
  const habitats = memoire(40, async (nom) => {
    const [a, b, c, d] = await Promise.all([...["a", "b", "c"].map((l) => couche(nom, l)),
      couche(nom, "d").catch(() => null)]);
    const [bx, by] = nom.split("_").map(Number);
    const n = B.taille * B.taille;
    const essence = new Uint8Array(n), protege = new Uint8Array(n), commune = new Uint16Array(n);
    const urbain = new Uint8Array(n);
    const foret = [];
    for (let i = 0; i < n; i++) {
      const q = i * 4;
      essence[i] = a.d[q + 2] & 15;
      protege[i] = c.d[q + 2];
      commune[i] = (c.d[q] << 8) | c.d[q + 1];
      urbain[i] = d ? d.d[q] >> 7 : 0;
      if (essence[i] > 0 && !urbain[i]) foret.push(i);
    }
    const nf = foret.length;
    const cases = {
      lat: new Float64Array(nf), lon: new Float64Array(nf), altitude: new Float64Array(nf),
      ensoleillement: new Float64Array(nf), pente: new Float64Array(nf), essence: new Uint8Array(nf),
      ouverte: new Uint8Array(nf), public: new Uint8Array(nf), roche: new Uint8Array(nf), orientation: new Uint8Array(nf),
      ph: new Uint8Array(nf),
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
      cases.ph[f] = d ? d.d[q] & 127 : 0;
    });
    return { nom, essence, protege, commune, urbain, foret: Int32Array.from(foret), cases, prep: null };
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

  // Une espèce des prés se peint commune par commune : la commune de chaque case (couche « c »
  // seule, légère) et l'indice moyen des prés de chaque commune (data/communes/<espèce>_<jour>.png).
  // La couche c, toujours en clair : la commune et la zone protégée de chaque case.
  const couchesC = memoire(60, async (nom) => {
    const c = await pixels(`habitat/blocs/${nom}_c.png`);
    const n = B.taille * B.taille, commune = new Uint16Array(n), protege = new Uint8Array(n);
    for (let i = 0; i < n; i++) {
      commune[i] = (c.d[i * 4] << 8) | c.d[i * 4 + 1];
      protege[i] = c.d[i * 4 + 2];
    }
    return { commune, protege };
  });
  const communesBloc = async (nom) => (await couchesC(nom)).commune;

  // Les zones de 250 m d'un bloc (champi/zones.py) : celles qui ont de la forêt, à plat, comme
  // les cases de la carte fine, avec leur habitat déjà calculé pour chaque espèce.
  const zoneDe = (lig, col) => Math.min(Math.floor(lig / Z.facteur), Z.n - 1) * Z.n
    + Math.min(Math.floor(col / Z.facteur), Z.n - 1);
  const zonesBloc = memoire(40, async (nom) => {
    const px = await pixels(`data/zones/${nom}.png`);
    const N = Z.n, NN = N * N, E = Z.especes.length;
    const plan = (p, i) => px.d[(p * NN + i) * 4];
    const [bx, by] = nom.split("_").map(Number);
    const y1 = (by + 1) * B.cote, x0 = bx * B.cote;
    // Centre d'une zone, en cases : la dernière de chaque ligne prend les 7 dernières cases.
    const centre = (r) => (r === N - 1 ? (r * Z.facteur + B.taille) / 2 : (r + 0.5) * Z.facteur);
    const drapeaux = new Uint8Array(NN), rang = new Int32Array(NN).fill(-1), avec = [];
    for (let i = 0; i < NN; i++) {
      drapeaux[i] = plan(E + 3, i);
      if (drapeaux[i] & 1) { rang[i] = avec.length; avec.push(i); }
    }
    const nz = avec.length;
    const cases = { lat: new Float64Array(nz), lon: new Float64Array(nz), altitude: new Float64Array(nz),
                    ensoleillement: new Float64Array(nz), habitat: {} };
    for (const code of Z.especes) cases.habitat[code] = new Float32Array(nz);
    avec.forEach((i, f) => {
      const r = Math.floor(i / N), q = i % N;
      cases.lat[f] = latDeY(y1 - centre(r) * B.pas);
      cases.lon[f] = (x0 + centre(q) * B.pas) / R * 180 / Math.PI;
      cases.altitude[f] = ((plan(E, i) << 8) | plan(E + 1, i)) - Z.altitude_decalage;
      cases.ensoleillement[f] = (plan(E + 2, i) - 100) / 100;
      Z.especes.forEach((code, k) => { cases.habitat[code][f] = plan(k, i) / 255; });
    });
    return { drapeaux, rang, cases, prep: null };
  });
  const tablesCommunes = memoire(4, async (cle) => {
    const px = await pixels(`data/communes/${cle}.png`);
    const v = new Uint8Array(px.l * px.h);
    for (let i = 0; i < v.length; i++) v[i] = px.d[i * 4];
    return v;
  });
  const codesCommunes = memoire(60, async (cle) => {
    const [nom, esp, k] = cle.split("|");
    const [commune, table] = await Promise.all([communesBloc(nom), tablesCommunes(`${esp}_${k}`)]);
    const codes = new Uint8Array(commune.length);
    for (let i = 0; i < codes.length; i++) codes[i] = commune[i] ? table[commune[i]] : 0;
    return codes;
  });

  // Codes d'un bloc pour l'espèce et le jour : un octet par case, comme l'aperçu. « Forêts
  // publiques seulement » laisse les autres sans couleur.
  const cleCodes = (nom, esp, k, publiques) => `${nom}|${esp}|${k}|${publiques ? 1 : 0}|${modeFin() ? 1 : 0}`;
  const codesBlocs = memoire(60, async (cle) => {
    const [nom, esp, k, publiques, fin] = cle.split("|");
    if (fin === "0") return codesZones(nom, esp, Number(k), publiques === "1");
    const [h, m] = await Promise.all([habitats(nom), meteos(nom)]);
    if (!h.prep) h.prep = preparer(h.cases, m);
    const ind = indices(especes[esp], h.prep, m, jourDe(Number(k)), communs);
    const codes = new Uint8Array(B.taille * B.taille);
    h.foret.forEach((i, f) => {
      if (publiques === "1" && !h.cases.public[f]) return;
      codes[i] = h.protege[i] ? PROTEGE : Math.min(carte.echelle, Math.round(ind[f] * carte.echelle));
    });
    return codes;
  });

  // La carte publique : l'indice de chaque zone de 250 m, peint sur toutes ses cases ; les cases
  // protégées des zones boisées restent hachurées (couche c, en clair).
  async function codesZones(nom, esp, k, publiques) {
    const [z, m, cc] = await Promise.all([zonesBloc(nom), meteos(nom), couchesC(nom)]);
    if (!z.prep) z.prep = preparer(z.cases, m);
    const ind = indices(especes[esp], z.prep, m, jourDe(k), communs);
    const parZone = new Uint8Array(Z.n * Z.n);
    z.rang.forEach((f, i) => {
      if (f >= 0 && !(publiques && !(z.drapeaux[i] & 2))) parZone[i] = Math.min(carte.echelle, Math.round(ind[f] * carte.echelle));
    });
    const codes = new Uint8Array(B.taille * B.taille);
    for (let lig = 0; lig < B.taille; lig++) {
      for (let col = 0; col < B.taille; col++) {
        const i = lig * B.taille + col, zi = zoneDe(lig, col);
        codes[i] = cc.protege[i] && (z.drapeaux[zi] & 4) ? PROTEGE : parZone[zi];
      }
    }
    return codes;
  }

  // Mode exploration : les cases boisées qui passent les filtres (essence, roche, altitude,
  // exposition, forêts publiques), sans météo ni saison, sur la même grille que l'indice.
  const RETENUE = 1;
  const codesFiltre = memoire(60, async (cle) => {
    const k = cle.indexOf("#");
    const nom = cle.slice(0, k), f = JSON.parse(cle.slice(k + 1));
    const h = await habitats(nom);
    const c = h.cases;
    const essences = new Set(f.essences), roches = new Set(f.roches), orientations = new Set(f.orientations);
    const codes = new Uint8Array(B.taille * B.taille);
    h.foret.forEach((i, q) => {
      if (!essences.has(c.essence[q]) || !roches.has(c.roche[q]) || !orientations.has(c.orientation[q])) return;
      if (c.altitude[q] < f.altitude[0] || c.altitude[q] > f.altitude[1] || (f.publique && !c.public[q])) return;
      codes[i] = h.protege[i] ? PROTEGE : RETENUE;
    });
    return codes;
  });

  // --- État ---------------------------------------------------------------------
  // Un lien d'une page de département (?departement=85&espece=cepe&jour=2026-11-03) l'emporte
  // sur ce que le navigateur a gardé ; le jour se donne par sa date, pas par son rang.
  const demande = new URLSearchParams(location.search);
  const depDemande = deps[demande.get("departement")]?.centre ? demande.get("departement") : null;
  const jourDemande = carte.jours.findIndex((j) => j.date === demande.get("jour"));
  const memoDep = lire(CLE_DEPARTEMENT);
  const etat = {
    departement: depDemande ?? (deps[memoDep]?.centre ? memoDep : "74"),
    espece: [demande.get("espece"), lire(CLE_ESPECE)].find((c) => especes[c]) ?? carte.especes[0].code,
    jour: jourDemande >= 0 ? jourDemande : jourDepart,
    filtre: null,       // mode exploration : les critères, ou null pour l'indice
    publiques: false,   // l'indice des seules forêts publiques (régime forestier)
  };

  // --- Feuille du bas (téléphone) --------------------------------------------------------
  // Repliée, elle montre la poignée, les espèces et les jours ; une case ouverte, son indice.
  let caseCourante = null;            // { ll, popup } : la case touchée, montrée
  let detailOuvert = false;           // le détail d'une case, ouvert une fois, le reste pour les suivantes
  const feuille = installerFeuille($("panneau"), $("poignee"), {
    bas: () => {
      const ref = caseCourante ? ($("case").querySelector(".score") ?? $("case")) : $("choix-jour");
      return ref.offsetTop + ref.offsetHeight + 12;
    },
  });

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
  const wmts = (couche, format, style = "normal", jeu = "PM") =>
    `https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&STYLE=${style}` +
    `&TILEMATRIXSET=${jeu}&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&LAYER=${couche}&FORMAT=${format}`;
  // Les fonds : le plan IGN grisé par défaut (les couleurs de l'indice ressortent), le même avec
  // l'estompage du relief (vallées, versants), ou les photographies aériennes. Le choix est gardé.
  const plan = () => L.tileLayer(wmts("GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2", "image/png"),
    { maxZoom: 19, className: "fond-gris", attribution: "Fond © IGN" });
  const fonds = {
    plan: [plan()],
    relief: [plan(), L.tileLayer(wmts("ELEVATION.ELEVATIONGRIDCOVERAGE.SHADOW", "image/png", "estompage_grayscale"),
      { maxZoom: 19, maxNativeZoom: 15, className: "estompage", attribution: "Relief © IGN" })],
    photo: [L.tileLayer(wmts("ORTHOIMAGERY.ORTHOPHOTOS", "image/jpeg"), { maxZoom: 19, attribution: "Photographies © IGN" })],
  };
  let fond = fonds[lire(CLE_FOND)] ? lire(CLE_FOND) : "plan";
  for (const c of fonds[fond]) c.addTo(map);
  // L'indice dans son calque, entre le fond et les marques (position, coins) : en mode « produit »
  // sur le plan et le relief, les noms et les routes du plan restent lisibles sous les couleurs
  // (style.css) ; pas sur les photos, qu'il assombrirait.
  map.createPane("indice").style.zIndex = 350;
  const marquerFond = () => map.getContainer().classList.toggle("sur-photo", fond === "photo");
  marquerFond();
  // Les contours des départements, au-dessus de l'indice et sous les marques (installés plus bas).
  map.createPane("contours").style.zIndex = 390;
  map.getPane("contours").style.pointerEvents = "none";
  map.attributionControl.addAttribution("Indice : météo Météo-France et ECMWF via Open-Meteo, forêts et relief IGN, roches BRGM");

  const ControleFonds = L.Control.extend({
    onAdd() {
      const div = L.DomUtil.create("div", "fonds");
      L.DomEvent.disableClickPropagation(div);
      for (const [cle, nom] of [["plan", "Plan"], ["relief", "Relief"], ["photo", "Photos"]]) {
        const bt = el("button", { type: "button", "aria-pressed": String(cle === fond) }, nom);
        bt.addEventListener("click", () => {
          for (const c of fonds[fond]) map.removeLayer(c);
          fond = cle;
          ecrire(CLE_FOND, cle);
          marquerFond();
          for (const c of fonds[cle]) c.addTo(map);
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

  // Une commune entière peinte (espèces des prés) : plus transparente, le fond reste lisible.
  const OPACITE_COMMUNES = 120;
  function peindre(o, p, code, hachure, alpha = 0) {
    if (code === PROTEGE) {             // hachures : « réglementation propre », jamais un gris plein
      if (hachure) { o[p] = pal.hachure[0]; o[p + 1] = pal.hachure[1]; o[p + 2] = pal.hachure[2]; o[p + 3] = 150; }
      return;
    }
    const t = code * 4;
    o[p] = TABLE[t]; o[p + 1] = TABLE[t + 1]; o[p + 2] = TABLE[t + 2];
    o[p + 3] = alpha && TABLE[t + 3] ? alpha : TABLE[t + 3];
  }

  // Vue large : l'aperçu national.
  const g = carte.apercu.grille;
  let apercu = null;
  const Apercu = L.GridLayer.extend({
    createTile(coords) {
      const tuile = document.createElement("canvas");
      tuile.width = tuile.height = 256;
      if (!apercu || etat.filtre) return tuile;   // l'exploration ne se lit que de près
      if (vueFrance()) return tuile;                // la vue France : les carrés (calqueCarres)
      const alpha = desPres(etat.espece) ? OPACITE_COMMUNES : 0;
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
          if (code <= carte.echelle) peindre(img.data, (j * 256 + i) * 4, code, false, alpha);
        }
      }
      ctx.putImageData(img, 0, 0);
      return tuile;
    },
  });
  const calqueApercu = new Apercu({ pane: "indice", maxZoom: DETAIL - 0.5, updateWhenZooming: false }).addTo(map);

  // Vue France (zoom sous SYNTHESE) : chaque carré de 9,2 km au verdict des départements, comme la
  // carte de l'accueil (export_france.verdicts_carres) et « Que chercher ici ? » (mêmes données,
  // data/vue) ; rien sous carre_min_km2 de forêt. Les espèces des prés gardent leurs communes.
  const NIVEAU_RVB = [[0xe2, 0xde, 0xd5], [0xef, 0xec, 0xe5], pal.classes[2], pal.classes[3], pal.classes[4]];
  const versLat = (y) => (2 * Math.atan(Math.exp(y / R)) - Math.PI / 2) * 180 / Math.PI;
  // Deux grilles : 9,2 km jusqu'au zoom 6,5, 4,6 km au zoom 7 (une case garde à peu près la même
  // taille à l'écran) ; sans vue_fine (export d'avant), la grande partout.
  const GRILLES = [carte.vue && { ...carte.vue, lire: vues },
                   carte.vue?.carre_min_km2 && carte.vue_fine && { ...carte.vue, ...carte.vue_fine, lire: vuesFines }]
    .filter(Boolean);
  let carres = null;                   // les verdicts de chaque grille, pour l'espèce et le jour affichés
  // Leaflet choisit ses tuiles au zoom arrondi (7,5 → 8) : la vue France s'arrête au même endroit.
  const vueFrance = () => carres !== null && Math.round(map.getZoom()) < SYNTHESE;
  const grilleCarres = () => (GRILLES.length > 1 && Math.round(map.getZoom()) >= CARRES_FINS ? 1 : 0);
  const kmCarre = (G) => Math.round(g.pas * G.facteur * Math.cos(46.5 * Math.PI / 180) / 1000);
  async function verdictsCarres(code, k, V) {
    const e = V ? V.especes.indexOf(code) : -1;
    if (e < 0 || !V.carre_min_km2) return null;
    const v = await V.lire(k);
    const n = V.nx * V.ny, pas = g.pas * V.facteur, jour = jourDe(k), sortie = new Int8Array(n);
    for (let l = 0; l < V.ny; l++) {
      const saison = facteurSaison(especes[code], jour, versLat(g.y1 - (l + 0.5) * pas), communs);
      for (let c = 0; c < V.nx; c++) {
        const i = l * V.nx + c;
        sortie[i] = v[i] / V.km2_par < V.carre_min_km2 ? -1
          : niveauZone(saison, v[(1 + 2 * e) * n + i] / V.parts_par, v[(2 + 2 * e) * n + i] / V.parts_par, carte.niveaux);
      }
    }
    return sortie;
  }
  const Carres = L.GridLayer.extend({
    createTile(coords) {
      const tuile = document.createElement("canvas");
      tuile.width = tuile.height = 256;
      if (!carres || etat.filtre) return tuile;
      const G = grilleCarres(), V = GRILLES[G], niveaux = carres[G], pas = g.pas * V.facteur;
      const { xs, ys } = axes(coords);
      const ctx = tuile.getContext("2d");
      const img = ctx.createImageData(256, 256);
      for (let j = 0; j < 256; j++) {
        const l = Math.floor((g.y1 - ys[j]) / pas);
        if (l < 0 || l >= V.ny) continue;
        for (let i = 0; i < 256; i++) {
          const c = Math.floor((xs[i] - g.x0) / pas);
          if (c < 0 || c >= V.nx) continue;
          const niv = niveaux[l * V.nx + c];
          if (niv < 0) continue;
          const p = (j * 256 + i) * 4;
          img.data.set(NIVEAU_RVB[niv], p);
          img.data[p + 3] = OPACITE;
        }
      }
      ctx.putImageData(img, 0, 0);
      return tuile;
    },
  });
  const calqueCarres = new Carres({ pane: "indice", maxZoom: SYNTHESE - 1, updateWhenZooming: false }).addTo(map);

  // Les contours des départements (ADMIN EXPRESS simplifié à ~2 km, data/departements_carte.json, ceux
  // de l'accueil et de la page des départements) : un trait sombre bordé de clair, lisible sur le
  // foncé comme sur le pâle, jusqu'au zoom 11 ; plus près, la simplification s'écarterait trop des
  // vraies limites (le plan IGN les montre). Remplace les noms de lieux de l'IGN (2026-11-07).
  const calqueContours = L.layerGroup();
  let lisere = null, trait = null;
  // Plus épais de près : sur la vue France, les départements sont petits et un trait épais boucherait.
  const epaisseurs = () => (map.getZoom() < CARRES_FINS ? [3, 1.4] : map.getZoom() < SYNTHESE ? [3.5, 1.8] : [4.5, 2.3]);
  const majContours = () => {
    const voir = map.getZoom() < CONTOURS_JUSQUA;
    if (voir !== map.hasLayer(calqueContours)) { if (voir) calqueContours.addTo(map); else map.removeLayer(calqueContours); }
    if (voir && trait) {
      const [l, t] = epaisseurs();
      lisere.setStyle({ weight: l });
      trait.setStyle({ weight: t });
    }
  };
  fetch("data/departements_carte.json").then((r) => (r.ok ? r.json() : null)).then((c) => {
    if (!c?.cadre) return;
    const [x0, y0, x1, y1] = c.cadre, kx = (x1 - x0) / c.largeur, ky = (y1 - y0) / c.hauteur;
    const versLL = (u, v) => [versLat(y1 - v * ky), ((x0 + u * kx) / R) * 180 / Math.PI];
    const anneaux = [];
    for (const d of Object.values(c.traces)) {
      for (const sous of d.split("M").filter(Boolean)) {   // « x y l dx dy dx dy … z », au dixième
        const n = sous.match(/-?\d+(?:\.\d+)?/g).map(Number);
        let u = n[0], v = n[1];
        const points = [versLL(u, v)];
        for (let i = 2; i + 1 < n.length; i += 2) { u += n[i]; v += n[i + 1]; points.push(versLL(u, v)); }
        points.push(points[0]);
        anneaux.push(points);
      }
    }
    const rendu = L.canvas({ pane: "contours", padding: 0.3 });
    lisere = L.polyline(anneaux, { renderer: rendu, interactive: false, color: "#ffffff", opacity: 0.85 }).addTo(calqueContours);
    trait = L.polyline(anneaux, { renderer: rendu, interactive: false, color: "#1d1b17", opacity: 1 }).addTo(calqueContours);
    majContours();
  }).catch((err) => console.error(err));
  map.on("zoomend", majContours);
  // Passer le seuil sans changer de niveau de tuiles garderait les tuiles d'avant.
  let coteFrance = vueFrance(), grilleVue = grilleCarres();
  map.on("zoomend", () => {
    if (vueFrance() !== coteFrance) { coteFrance = vueFrance(); calqueApercu.redraw(); legende(); }
    if (grilleCarres() !== grilleVue) { grilleVue = grilleCarres(); legende(); }   // ses tuiles changent de niveau
  });

  // Vue rapprochée : chaque tuile réunit les blocs qu'elle touche, calculés à la demande.
  const Detail = L.GridLayer.extend({
    createTile(coords, fini) {
      const tuile = document.createElement("canvas");
      tuile.width = tuile.height = 256;
      const { xs, ys } = axes(coords);
      const filtre = etat.filtre;
      const codesDe = filtre
        ? (nom) => codesFiltre(`${nom}#${JSON.stringify(filtre)}`)
        : desPres(etat.espece) ? (nom) => codesCommunes(`${nom}|${etat.espece}|${etat.jour}`)
          : (nom) => codesBlocs(cleCodes(nom, etat.espece, etat.jour, etat.publiques));
      const [er, eg, eb] = pal.exploration;
      const alpha = !filtre && desPres(etat.espece) ? OPACITE_COMMUNES : 0;
      const noms = new Set();
      for (const x of [xs[0], xs[255]]) for (const y of [ys[0], ys[255]]) {
        const nom = `${Math.floor(x / B.cote)}_${Math.floor(y / B.cote)}`;
        if (blocsPresents.has(nom)) noms.add(nom);
      }
      if (!noms.size) { setTimeout(() => fini(null, tuile)); return tuile; }
      Promise.all([...noms].map((nom) => codesDe(nom).then((c) => [nom, c])))
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
              const p = (j * 256 + i) * 4;
              if (filtre && code === RETENUE) {
                img.data[p] = er; img.data[p + 1] = eg; img.data[p + 2] = eb; img.data[p + 3] = OPACITE;
                continue;
              }
              peindre(img.data, p, code, (coords.x * 256 + i + coords.y * 256 + j) % 7 < 2, alpha);
            }
          }
          ctx.putImageData(img, 0, 0);
          fini(null, tuile);
        })
        .catch((e) => { console.error(e); fini(null, tuile); });
      return tuile;
    },
  });
  // minZoom à DETAIL - 0,5 : Leaflet crée les tuiles au zoom arrondi (10,5 → 11) mais les retire au
  // zoom exact sous minZoom ; à DETAIL, le zoom 10,5 restait vide (ni aperçu, ni détail).
  const calqueDetail = new Detail({ pane: "indice", minZoom: DETAIL - 0.5, updateWhenZooming: false, keepBuffer: 1 }).addTo(map);

  // Indice d'un coin noté par l'utilisateur, pour le jour affiché : moyenne des cases boisées
  // à moins de 75 m (3 × 3 cases), tirée des mêmes codes que la carte.
  async function indiceEn(lat, lon, code) {
    if (desPres(code)) return { pre: true };
    const [x, y] = versMerc(lat, lon);
    const bx = Math.floor(x / B.cote), by = Math.floor(y / B.cote);
    const nom = `${bx}_${by}`;
    if (!blocsPresents.has(nom)) return null;
    const col = Math.floor((x - bx * B.cote) / B.pas), lig = Math.floor(((by + 1) * B.cote - y) / B.pas);
    if (!modeFin()) {               // la zone de 250 m du coin
      const [z, codes, cc, communes] = await Promise.all([zonesBloc(nom), codesBlocs(cleCodes(nom, code, etat.jour, false)),
        couchesC(nom), annexes("habitat/communes.json")]);
      const i = lig * B.taille + col;
      const protege = codes[i] === PROTEGE;
      return { indice: !protege && z.rang[zoneDe(lig, col)] >= 0 ? codes[i] / carte.echelle : null, protege,
               commune: communes[cc.commune[i] - 1]?.nom };
    }
    const [h, codes, communes] = await Promise.all([
      habitats(nom), codesBlocs(cleCodes(nom, code, etat.jour, false)), annexes("habitat/communes.json")]);
    let s = 0, n = 0, protege = false;
    for (let l = Math.max(0, lig - 1); l <= Math.min(B.taille - 1, lig + 1); l++) {
      for (let c = Math.max(0, col - 1); c <= Math.min(B.taille - 1, col + 1); c++) {
        const i = l * B.taille + c;
        if (h.protege[i]) protege = true;
        else if (h.essence[i] > 0 && !h.urbain[i]) { s += codes[i] / carte.echelle; n++; }
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
  const alertes = installerAlertes({ carte, etat: () => ({ departement: etat.departement, espece: etat.espece }) });

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
    const [commune, communes] = await Promise.all([communesBloc(nom), annexes("habitat/communes.json")]);
    const col = Math.floor((x - bx * B.cote) / B.pas), lig = Math.floor(((by + 1) * B.cote - y) / B.pas);
    const com = communes[commune[lig * B.taille + col] - 1];
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
        // À l'ouverture, un département demandé par le lien ou choisi entre-temps l'emporte.
        if (depAuto && (depDemande || etat.departement !== depOuverture)) return;
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
    // « Autour de moi » (accueil, carte/?autour) : la carte se centre sur la position, et dit
    // pourquoi si elle est refusée.
    if (demande.has("autour")) { activer({ centrer: true, auto: false }); return; }
    try {
      if ((await navigator.permissions?.query({ name: "geolocation" }))?.state === "denied") return;
    } catch { /* sans l'API des permissions : on demande */ }
    activer({ centrer: false, auto: true });
  }

  async function rafraichirCalques() {
    $("bandeau-pres").hidden = !desPres(etat.espece);
    if (desPres(etat.espece)) {
      $("bandeau-pres").textContent = `${especes[etat.espece].nom} : les prés sont presque tous privés, la carte ` +
        "ne les note pas un par un. Chaque commune prend la couleur de l'ensemble de ses prés.";
    }
    const demande = `${etat.espece}_${etat.jour}`;
    const [a, c] = await Promise.all([apercus(demande),
      Promise.all(GRILLES.map((G) => verdictsCarres(etat.espece, etat.jour, G)))
        .then((l) => (l.length && l.every(Boolean) ? l : null))
        .catch((err) => { console.error(err); return null; })]);
    if (demande !== `${etat.espece}_${etat.jour}`) return;   // l'utilisateur a déjà changé d'avis
    apercu = a;
    carres = c;
    coteFrance = vueFrance();
    calqueApercu.redraw();
    calqueCarres.redraw();
    legende();
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
    if (centrer && d.bornes) {
      map.fitBounds([[d.bornes[0], d.bornes[1]], [d.bornes[2], d.bornes[3]]]);
      if (feuille.etroit()) feuille.poser("bas");
    }
    if (centrer) onglet("departement");
    resume = await resumes(code);
    if (etat.departement === code) panneau();
  }

  // L'espèce : le bouton du panneau (son dessin, son nom, son état dans le département) ouvre la
  // liste illustrée, en saison d'abord, au verdict du département pour le jour choisi.
  const icone = (code, taille = 40) => el("img", { class: "icone", src: `img/especes/${code}.svg`, alt: "",
    width: String(taille), height: String(taille) });
  function choixEspeces() {
    const e = especes[etat.espece];
    const r = resume?.[e.code]?.[etat.jour];
    $("choix-espece-icone").src = `img/especes/${e.code}.svg`;
    $("choix-espece-nom").textContent = e.nom;
    $("choix-espece-niv").textContent = r ? NIVEAU_COURT[r.niveau] : "";
    $("choix-espece-niv").className = `niv n${r ? r.niveau : "x"}`;
    const d = deps[etat.departement];
    $("dialogue-especes-sous-titre").textContent = `Les conditions en ${d?.nom ?? "France"}, ${carte.jours[etat.jour].libelle}`;
    const lignes = carte.especes.map((x, rang) => ({ x, rang, n: resume?.[x.code]?.[etat.jour]?.niveau ?? -1 }));
    const groupe = (titre, liste) => liste.length ? [el("h3", {}, titre), ...liste.map(({ x, n }) => el("button", {
      type: "button", class: `espece-choix${x.code === etat.espece ? " choisi" : ""}${n === 0 ? " hors" : ""}`,
      "aria-pressed": String(x.code === etat.espece),
      onclick: () => { $("dialogue-especes").close(); choisirEspece(x.code); },
    }, icone(x.code), el("span", { class: "nom" }, el("strong", {}, x.nom), el("em", {}, x.latin),
      desPres(x.code) ? el("span", { class: "milieu" }, "des prés, par commune") : ""),
    el("span", { class: `niv n${n < 0 ? "x" : n}` }, n < 0 ? "—" : NIVEAU_COURT[n])))] : [];
    const enSaison = lignes.filter((l) => l.n !== 0).sort((a, b) => b.n - a.n || a.rang - b.rang);
    $("liste-especes").replaceChildren(...groupe("En saison", enSaison), ...groupe("Hors saison", lignes.filter((l) => l.n === 0)));
  }
  $("choix-espece-bouton").addEventListener("click", () => {
    $("dialogue-especes").showModal();
    $("liste-especes").querySelector(".choisi")?.focus();
  });
  $("dialogue-especes-fermer").addEventListener("click", () => $("dialogue-especes").close());
  $("dialogue-especes").addEventListener("click", (ev) => {      // un clic à côté de la liste la ferme
    if (ev.target === ev.currentTarget) ev.currentTarget.close();
  });

  // Sur téléphone, les choix tiennent sur une ligne qui défile : le choix courant au milieu.
  function enVue(zone) {
    const c = zone.querySelector("label:has(input:checked)");
    if (c && zone.scrollWidth > zone.clientWidth) {
      zone.scrollLeft += c.getBoundingClientRect().left - zone.getBoundingClientRect().left - (zone.clientWidth - c.offsetWidth) / 2;
    }
  }

  function choisirEspece(code) {
    etat.espece = code;
    ecrire(CLE_ESPECE, code);
    tout();
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
    enVue(zone);
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
    if (e.avertissement) corps.push(el("p", {}, el("strong", {}, e.avertissement)));
    corps.push(el("p", { class: "muet" }, "Ce portrait ne suffit jamais pour identifier un champignon."));
    const photo = el("img", { class: "photo-fiche", src: `img/especes/${e.code}.jpg`, alt: e.nom, loading: "lazy" });
    photo.addEventListener("error", () => { photo.src = `img/especes/${e.code}.svg`; }, { once: true });
    $("fiche").replaceChildren(
      el("h3", {}, e.nom, " ", el("span", { class: "latin" }, e.latin)), photo, ...corps,
      el("p", {}, el("a", { href: `especes/${e.code}.html` }, "La fiche complète : saison, milieux, sosies, vérification")));
  }

  // La semaine du département : le niveau de chaque espèce, jour par jour (celui du verdict).
  // Un clic affiche l'espèce et le jour sur la carte.
  function semaine() {
    const tete = el("tr", {}, el("th", {}, ""), ...carte.jours.map((j, k) => {
      const d = new Date(`${j.date}T12:00:00`);
      return el("th", { scope: "col", title: j.libelle, class: k === etat.jour ? "actuel" : "" },
        d.toLocaleDateString("fr-FR", { weekday: "short" }), el("br"), String(d.getDate()));
    }));
    const lignes = carte.especes.map((e) => el("tr", {}, el("th", desPres(e.code)
      ? { scope: "row", class: "pre", title: "Espèce des prés : ses prés, sans carte fine" } : { scope: "row" }, e.nom),
      ...carte.jours.map((j, k) => {
        const r = resume?.[e.code]?.[k];
        const texte = `${e.nom}, ${j.libelle} : ${r ? r.verdict.toLowerCase() : "pas de forêt calculée"}`;
        const choisi = e.code === etat.espece && k === etat.jour;
        return el("td", {}, el("button", {
          type: "button", class: `niveau n${r ? r.niveau : "x"}${choisi ? " choisi" : ""}`,
          title: texte, "aria-label": texte,
          onclick: () => { etat.jour = k; choisirEspece(e.code); },
        }, r?.niveau === 0 ? "–" : ""));
      })));
    $("semaine").replaceChildren(el("thead", {}, tete), el("tbody", {}, ...lignes));
    const d = deps[etat.departement];
    const page = `departements/${etat.departement}.html`;
    $("lien-departement").replaceChildren(...(d ? [
      el("a", { href: page }, `La semaine en ${d.nom}, sur une page à part`), " · ",
      el("button", { type: "button", class: "lien", onclick: (ev) => partager(
        { titre: `Champignons en ${d.nom} : les conditions de la semaine`, url: new URL(page, document.baseURI).href },
        ev.currentTarget) }, "Partager"),
    ] : []));
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
      $("verdict-titre").textContent = desPres(etat.espece) ? "Pas de pré calculé dans ce département."
        : "Pas de forêt calculée dans ce département.";
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

  // Que chercher ici ? Les espèces classées pour la zone affichée (ici.js), au verdict des
  // départements ; une zone plus petite qu'un pixel de 9,2 km prend le pixel qui la contient.
  let tourIci = 0;
  async function queChercherIci() {
    const V = carte.vue;
    if (!V) return;
    const moi = ++tourIci, k = etat.jour;
    let v;
    try { v = await vues(k); } catch (err) { console.error(err); return; }
    if (moi !== tourIci) return;
    const b = map.getBounds(), pas = g.pas * V.facteur;
    const [xo, ys] = versMerc(b.getSouth(), b.getWest());
    const [xe, yn] = versMerc(b.getNorth(), b.getEast());
    const zone = { c0: Math.floor((xo - g.x0) / pas), c1: Math.floor((xe - g.x0) / pas),
                   l0: Math.floor((g.y1 - yn) / pas), l1: Math.floor((g.y1 - ys) / pas) };
    const { surface, parts } = partsZone(v, V, zone);
    const lat = map.getCenter().lat, jour = jourDe(k);
    const liste = V.especes.filter((code) => especes[code]).map((code) => ({ code, ...parts[code],
      n: niveauZone(facteurSaison(especes[code], jour, lat, communs), parts[code].bon, parts[code].moyen, carte.niveaux) }))
      .sort((a, b) => b.n - a.n || b.bon - a.bon || b.moyen - a.moyen);
    const ol = $("ici");
    ol.replaceChildren();
    const petite = (zone.c1 - zone.c0 + 1) * (zone.l1 - zone.l0 + 1) <= 4;
    $("ici-texte").textContent = surface ? `Dans les forêts de la zone affichée${petite ? " et autour (9 km)" : ""}, ` +
      `${carte.jours[k].libelle}, au même verdict que les départements. Un clic choisit l'espèce.` : "";
    if (!surface) { ol.append(el("li", { class: "muet" }, "Pas de forêt calculée dans la zone affichée.")); return; }
    for (const x of liste) {
      ol.append(el("li", {}, el("button", { type: "button", class: x.code === etat.espece ? "choisi" : "",
        "aria-pressed": String(x.code === etat.espece), onclick: () => choisirEspece(x.code) },
        el("span", { class: "nom" }, icone(x.code, 26), el("span", { class: `pastille n${x.n}` }), especes[x.code].nom),
        el("span", { class: "cl" }, NIVEAU_COURT[x.n]))));
    }
  }
  let attenteIci = null;
  map.on("moveend", () => { clearTimeout(attenteIci); attenteIci = setTimeout(queChercherIci, 250); });

  function allerA(centre) {
    map.setView(centre, 13);
    if (feuille.etroit()) feuille.poser("bas");
  }

  function legende() {
    const z = $("legende");
    z.replaceChildren();
    if (vueFrance()) {
      for (const n of [4, 3, 2, 1, 0]) {
        z.append(el("div", {}, el("span", { class: `pastille n${n}` }), NIVEAU_COURT[n][0].toUpperCase() + NIVEAU_COURT[n].slice(1)));
      }
      z.append(el("div", {}, el("span", { class: "pastille vide" }), "Sans couleur : trop peu de forêt dans le carré"));
      z.append(el("p", { class: "muet" }, `Vue France : chaque carré d'environ ${kmCarre(GRILLES[grilleCarres()])} km au verdict des départements ` +
        `(« bon » dès ${Math.round(carte.niveaux.bon * 100)} % de sa forêt à l'indice bon). Zoomez pour l'indice, forêt par forêt.`));
      return;
    }
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
    z.append(el("p", { class: "muet" }, `En vue régionale, chaque pixel d'environ 1 km prend la meilleure forêt qu'il ` +
      "contient ; zoomez pour voir " +
      (modeFin() ? "les cases de 50 m." : "les zones de 250 m (l'habitat le plus favorable de chacune).")));
  }

  // La carte fine : le mot de passe donne la clé, gardée sur l'appareil ; la carte passe des
  // zones de 250 m aux cases de 50 m. « Revenir aux zones » oublie la clé.
  function installerFine() {
    if (!Z || !carte.fine) return;          // pas de carte fine publiée, ou essai sur le poste
    $("fine").hidden = false;
    const afficher = () => {
      $("fine-etat").textContent = cleFine
        ? "Cases de 50 m sur cet appareil. La clé y reste gardée : le mot de passe ne se redemande pas."
        : "La carte montre des zones de 250 m. Avec le mot de passe, elle passe aux cases de 50 m, sur cet appareil.";
      $("fine-form").hidden = Boolean(cleFine);
      $("fine-oublier").hidden = !cleFine;
    };
    const basculer = () => {
      if (!modeFin() && etat.filtre) { etat.filtre = null; $("explorer-actif").checked = false; }
      afficher();
      legende();
      calqueDetail.redraw();
      afficherCase();
      coins.rafraichir();
    };
    $("fine-form").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const bouton = $("fine-form").querySelector("button");
      bouton.disabled = true;
      $("fine-message").textContent = "Vérification…";
      try {
        const { brut, id } = await deriver($("fine-mot").value, carte.fine);
        if (id !== carte.fine.id) {
          $("fine-message").textContent = "Ce n'est pas le bon mot de passe.";
          return;
        }
        cleFine = await importer(brut);
        garder(id, brut);
        $("fine-mot").value = "";
        $("fine-message").textContent = "";
        basculer();
      } catch (err) {
        console.error(err);
        $("fine-message").textContent = "Le déverrouillage n'a pas pu se faire dans ce navigateur.";
      } finally {
        bouton.disabled = false;
      }
    });
    $("fine-oublier").addEventListener("click", () => {
      cleFine = null;
      oublier();
      basculer();
    });
    afficher();
  }

  function antipoison() {
    const c = map.getCenter();
    const [ville, , , tel] = CENTRES_ANTIPOISON.reduce((m, v) =>
      (Math.hypot(v[1] - c.lat, (v[2] - c.lng) * 0.7) < Math.hypot(m[1] - c.lat, (m[2] - c.lng) * 0.7) ? v : m));
    $("antipoison").textContent = `centre antipoison le plus proche (${ville}) : ${tel}`;
  }
  map.on("moveend", antipoison);
  // Déplacer la carte replie la feuille : la carte d'abord.
  map.on("dragstart", () => { if (feuille.etroit() && feuille.etat() !== "bas") feuille.poser("bas"); });

  // --- Fenêtre d'une case ---------------------------------------------------------
  // Sur ordinateur, une fenêtre au-dessus de la case ; sur téléphone, la feuille du bas, à
  // mi-hauteur, et un cercle sur la case. Changer d'espèce ou de jour la recalcule.
  const calqueCase = L.layerGroup().addTo(map);
  map.on("click", (ev) => {
    if (map.getZoom() < DETAIL) { map.setView(ev.latlng, DETAIL + 1); return; }
    const [x, y] = versMerc(ev.latlng.lat, ev.latlng.lng);
    if (!blocsPresents.has(`${Math.floor(x / B.cote)}_${Math.floor(y / B.cote)}`)) return;
    if (feuille.etroit()) {
      caseCourante = { ll: ev.latlng, popup: null };
      calqueCase.clearLayers();
      L.circleMarker(ev.latlng, { radius: 10, color: "#1d1b17", weight: 3, fill: false, interactive: false }).addTo(calqueCase);
      remplirCase("Chargement…");
      feuille.poser("milieu");
      $("panneau").scrollTop = 0;
      // La case reste visible au-dessus de la feuille.
      const yCase = map.latLngToContainerPoint(ev.latlng).y, libre = innerHeight - feuille.hauteur("milieu");
      if (yCase > libre - 40) map.panBy([0, yCase - libre / 2]);
    } else {
      caseCourante = { ll: ev.latlng, popup: L.popup({ maxWidth: 300 }).setLatLng(ev.latlng).setContent("Chargement…").openOn(map) };
    }
    afficherCase();
  });
  map.on("popupclose", (ev) => { if (ev.popup === caseCourante?.popup) caseCourante = null; });

  async function afficherCase() {
    const c = caseCourante;
    if (!c) return;
    const montrer = (contenu) => { if (caseCourante === c) (c.popup ? c.popup.setContent(contenu) : remplirCase(contenu)); };
    const [x, y] = versMerc(c.ll.lat, c.ll.lng);
    const bx = Math.floor(x / B.cote), by = Math.floor(y / B.cote);
    const nom = `${bx}_${by}`;
    const i = Math.floor(((by + 1) * B.cote - y) / B.pas) * B.taille + Math.floor((x - bx * B.cote) / B.pas);
    try {
      if (desPres(etat.espece)) {
        const [commune, table, communes] = await Promise.all([
          communesBloc(nom), tablesCommunes(`${etat.espece}_${etat.jour}`), annexes("habitat/communes.json")]);
        montrer(fenetreCommune(commune[i], table[commune[i]], communes, c.ll));
        return;
      }
      if (!modeFin()) {
        const [z, m, cc, communes, infos] = await Promise.all([zonesBloc(nom), meteos(nom), couchesC(nom),
          annexes("habitat/communes.json"), annexes("habitat/blocs.json")]);
        montrer(fenetreZone(z, m, cc, i, communes, infos.blocs[nom], c.ll));
        return;
      }
      const [h, m, communes, zones] = await Promise.all([
        habitats(nom), meteos(nom), annexes("habitat/communes.json"), annexes("habitat/blocs.json")]);
      montrer(fenetre(h, m, i, communes, zones.blocs[nom], c.ll));
    } catch (err) {
      console.error(err);
      montrer("Les détails de cette case n'ont pas pu se charger.");
    }
  }

  function remplirCase(contenu) {
    const zone = $("case");
    zone.replaceChildren(el("button", { type: "button", class: "fermer", "aria-label": "Fermer la case",
      onclick: fermerCase }, "×"), contenu);
    zone.hidden = false;
  }

  function fermerCase() {
    caseCourante = null;
    calqueCase.clearLayers();
    $("case").hidden = true;
    $("case").replaceChildren();
    feuille.poser("bas");
  }

  // La fenêtre d'une case, en tuiles : l'indice sur 100 et sa classe, ce qui le retient, puis
  // chaque facteur, la propriété de la forêt et les actions (y aller, noter, Géoportail).
  function fenetre(h, meteo, i, communes, infoBloc, ll) {
    const e = especes[etat.espece];
    const com = communes[h.commune[i] - 1];
    const div = el("div", { class: "case-fenetre" });
    if (!com) {
      div.append(el("p", {}, "Hors de France : pas d'indice."));
      return div;
    }
    div.append(el("h4", {}, `${com.nom} (${com.dep})`));
    if (h.protege[i]) {
      div.append(...messageProtege(infoBloc, h.protege[i]));
      return div;
    }
    const f = h.foret.indexOf(i);
    if (f < 0) {
      div.append(el("p", {}, h.urbain[i] && h.essence[i]
        ? "Bois en zone urbanisée (parc, quartier, zone d'activités) : pas d'indice."
        : "Hors forêt : pas d'indice."), boutonCoin(ll));
      return div;
    }
    const k = h.cases;
    const cas = { essence: k.essence[f], ouverte: k.ouverte[f], roche: k.roche[f], altitude: k.altitude[f],
                  pente: k.pente[f], ensoleillement: k.ensoleillement[f], lat: k.lat[f], lon: k.lon[f], ph: k.ph[f] };
    const jour = jourDe(etat.jour);
    const r = evaluer(e, cas, meteo, jour, communs);
    div.append(score(r.indice));
    div.append(el("p", { class: "raison" }, ...raison(e, r, cas, jour)));
    div.append(el("p", { class: `statut ${k.public[f] ? "public" : "prive"}` },
      el("strong", {}, k.public[f] ? "Forêt publique" : "Forêt probablement privée"),
      k.public[f] ? " : cueillette familiale tolérée en général, dans la limite des arrêtés. "
        : " : les champignons sont au propriétaire, il faut son accord. ",
      el("a", { href: "avant-de-partir.html#proprietaire" }, "Les règles")));
    div.append(liensItineraire(ll.lat, ll.lng));
    div.append(actionsCase(ll, com));

    const p = r.parts;
    const affinite = (v) => `affinité ${v >= 0.8 ? "élevée" : v >= 0.5 ? "moyenne" : "faible"}`;
    const { tuiles, tuile } = fabriqueTuiles();
    tuile("Forêt", `${leg.essences[cas.essence]}${cas.ouverte ? ", ouverte" : ""}`, affinite(p.essence),
      p.essence * p.ouverte);
    tuile("Sol", p.parLePh ? `pH ${fr1.format(cas.ph / 10)}` : leg.roches[cas.roche],
      p.parLePh ? `${affinite(p.sol)} ; pH estimé, roche ${leg.roches[cas.roche].toLowerCase()}`
        : `${affinite(p.sol)}${cas.ph > 0 ? ` ; pH estimé ${fr1.format(cas.ph / 10)}` : ""}`, p.sol);
    const basse = p.plancher !== null && cas.altitude < p.plancher;      // une espèce de montagne
    tuile("Altitude", `${fr.format(cas.altitude)} m`, p.altitude >= 1
      ? (p.plancher !== null ? `pleine de ${fr.format(p.plancher)} à ${fr.format(p.plafond)} m ici`
        : `pleine jusqu'à ${fr.format(p.plafond)} m ici`)
      : basse ? (p.altitude > 0 ? "un peu basse pour l'espèce" : "trop basse pour l'espèce")
        : p.altitude > 0 ? "près de son plafond" : "au-dessus de son plafond", p.altitude);
    tuile("Exposition", leg.orientations[k.orientation[f]], `pente ${fr.format(cas.pente)}°`, p.pente);
    tuilesMeteo(tuile, e, r, jour, cas.lat);
    div.append(detailCase(tuiles, `Indice ${e.de}, ${carte.jours[etat.jour].libelle}. Case de 50 m ; météo AROME à 2,5 km.`));
    return div;
  }

  // La pluie, le sol, le gel et la saison : les mêmes tuiles pour une case et pour une zone.
  function tuilesMeteo(tuile, e, r, jour, lat) {
    const [, p1] = e.pluie_mm;
    const [, s1, s2] = e.sol;
    const [jmin, jmax] = e.pluie_jours;
    tuile("Pluie", `${fr.format(r.pluie)} mm`, `entre ${jmax} et ${jmin} jours avant ; pleine pousse dès ${fr.format(p1)} mm`,
      r.facteurs.pluie);
    tuile("Sol, 7 jours", `${fr1.format(r.tSol)} °C`, r.tSol < s1 ? `trop froid : il faut ${fr.format(s1)} °C`
      : r.tSol > s2 ? `trop chaud : au-delà de ${fr.format(s2)} °C` : `de ${fr.format(s1)} à ${fr.format(s2)} °C : bien`,
      r.facteurs.sol);
    tuile("Gel", r.gel ? `${r.gel} jour${r.gel > 1 ? "s" : ""}` : "Aucun", "sur les 7 derniers jours", r.facteurs.gel);
    const [, b, c] = datesSaison(e, jour.annee, lat, communs);
    tuile("Saison", phaseSaison(e, r.saison, jour, lat), `plein du ${jourEnMots(b)} au ${jourEnMots(c)} ici`, r.saison);
  }

  // Le détail des facteurs, replié : la fenêtre reste petite et ne déplace pas la carte.
  function detailCase(tuiles, note) {
    const detail = el("details", { class: "detail-case" }, el("summary", {}, "Le détail : forêt, sol, pluie…"), tuiles,
      el("p", { class: "muet" }, note));
    detail.open = detailOuvert;
    detail.addEventListener("toggle", () => {
      detailOuvert = detail.open;
      caseCourante?.popup?.update();      // la fenêtre grandit vers le haut : rester dans la carte
    });
    return detail;
  }

  function messageProtege(infoBloc, n) {
    const z = infoBloc?.protections?.[n - 1];
    return [el("p", {}, `${z ? `${z.nature} « ${z.nom} »` : "Zone protégée"}. Ces espaces ont leur propre ` +
      "réglementation, souvent plus stricte sur la cueillette : renseignez-vous avant d'y ramasser quoi que ce soit. " +
      "Le site n'y calcule pas d'indice."), el("p", {}, el("a", { href: "avant-de-partir.html#zones-protegees" }, "Les règles"))];
  }

  function fabriqueTuiles() {
    const qualite = (v) => (v >= 0.8 ? "ok" : v >= 0.5 ? "moyen" : "ko");
    const tuiles = el("div", { class: "tuiles" });
    const tuile = (titre, valeur, note, v) => tuiles.append(el("div", { class: `tuile ${qualite(v)}` },
      el("span", { class: "t" }, titre), el("strong", {}, valeur), el("span", { class: "n" }, note)));
    return { tuiles, tuile };
  }

  function score(v) {
    const kc = classeDe(v, carte.classes);
    return el("div", { class: "score" },
      el("span", { class: "score-valeur" }, String(Math.round(v * 100)), el("small", {}, " /100")),
      el("span", { class: "score-classe" }, carte.classes[kc].nom), jauge(v));
  }

  function actionsCase(ll, com) {
    const actions = el("p", { class: "actions-case" }, boutonCoin(ll), " · ", el("a", {
      href: `https://www.geoportail.gouv.fr/carte?c=${ll.lng.toFixed(5)},${ll.lat.toFixed(5)}&z=16&permalink=yes`,
      target: "_blank", rel: "noopener",
    }, "Géoportail (IGN)"));
    if (com.dep !== etat.departement && deps[com.dep]) {
      actions.append(" · ", el("button", { type: "button", class: "lien", onclick: () => allerDepartement(com.dep, false) },
        `Résumé : ${deps[com.dep].nom}`));
    }
    return actions;
  }

  // La fenêtre d'une zone de 250 m (carte publique) : son indice, ce qui le retient, la météo.
  // L'habitat est le plus favorable de la zone ; ni essence, ni roche, ni pente : c'est la carte fine.
  function fenetreZone(z, meteo, cc, i, communes, infoBloc, ll) {
    const e = especes[etat.espece];
    const com = communes[cc.commune[i] - 1];
    const div = el("div", { class: "case-fenetre" });
    if (!com) {
      div.append(el("p", {}, "Hors de France : pas d'indice."));
      return div;
    }
    div.append(el("h4", {}, `${com.nom} (${com.dep})`));
    const zi = zoneDe(Math.floor(i / B.taille), i % B.taille), f = z.rang[zi];
    if (cc.protege[i] && (z.drapeaux[zi] & 4)) {
      div.append(...messageProtege(infoBloc, cc.protege[i]));
      return div;
    }
    if (f < 0) {
      div.append(el("p", {}, "Pas de forêt dans cette zone de 250 m : pas d'indice."), boutonCoin(ll));
      return div;
    }
    const k = z.cases;
    const cas = { habitat: k.habitat[e.code][f], altitude: k.altitude[f], ensoleillement: k.ensoleillement[f],
                  lat: k.lat[f], lon: k.lon[f] };
    const jour = jourDe(etat.jour);
    const r = evaluer(e, cas, meteo, jour, communs);
    div.append(score(r.indice));
    div.append(el("p", { class: "raison" }, ...raison(e, r, cas, jour)));
    const publique = z.drapeaux[zi] & 2;
    div.append(el("p", { class: `statut ${publique ? "public" : "prive"}` },
      el("strong", {}, publique ? "Surtout des forêts publiques" : "Surtout des forêts privées"),
      publique ? " : cueillette familiale tolérée en général, dans la limite des arrêtés. "
        : " : les champignons sont au propriétaire, il faut son accord. ",
      el("a", { href: "avant-de-partir.html#proprietaire" }, "Les règles")));
    div.append(liensItineraire(ll.lat, ll.lng));
    div.append(actionsCase(ll, com));
    const { tuiles, tuile } = fabriqueTuiles();
    tuile("Habitat", `${Math.round(r.habitat * 100)} /100`, "forêt, sol, altitude et pente : le meilleur de la zone",
      r.habitat);
    tuile("Altitude", `${fr.format(cas.altitude)} m`, "moyenne des forêts de la zone", 1);
    tuilesMeteo(tuile, e, r, jour, cas.lat);
    div.append(detailCase(tuiles, `Indice ${e.de}, ${carte.jours[etat.jour].libelle}. Zone de 250 m : l'habitat le ` +
      "plus favorable de la zone, la météo à son altitude moyenne (AROME à 2,5 km)." +
      (carte.fine ? " Les cases de 50 m : carte fine, dans Mes outils." : "")));
    return div;
  }

  // Une espèce des prés : la commune touchée et l'indice moyen de ses prés, jamais un pré.
  function fenetreCommune(n, code, communes, ll) {
    const e = especes[etat.espece];
    const com = communes[n - 1];
    const div = el("div", { class: "case-fenetre" });
    if (!com) {
      div.append(el("p", {}, "Hors de France : pas d'indice."));
      return div;
    }
    div.append(el("h4", {}, `${com.nom} (${com.dep})`));
    if (code > carte.echelle) {
      div.append(el("p", {}, `Trop peu de prés dans cette commune pour noter les conditions ${e.de}.`), boutonCoin(ll));
      return div;
    }
    const v = code / carte.echelle, kc = classeDe(v, carte.classes);
    div.append(el("div", { class: "score" },
      el("span", { class: "score-valeur" }, String(Math.round(v * 100)), el("small", {}, " /100")),
      el("span", { class: "score-classe" }, carte.classes[kc].nom), jauge(v)));
    div.append(el("p", { class: "muet score-jour" }, `Indice moyen des prés de la commune, pour ${e.nom.toLowerCase()}, ` +
      `${carte.jours[etat.jour].libelle}`));
    div.append(el("p", {}, "Les prés sont presque tous privés : la carte ne les note pas un par un. Dans un pré, " +
      "les champignons appartiennent au propriétaire, il faut son accord. ",
      el("a", { href: "avant-de-partir.html#proprietaire" }, "Les règles")));
    div.append(el("p", { class: "actions-case" }, boutonCoin(ll)));
    return div;
  }

  // L'indice sur 100 et sa place parmi les classes (seuils fixes) : 45 n'est pas « moyen », c'est « bon ».
  function jauge(v) {
    const z = el("div", { class: "jauge", role: "img", "aria-label": `${Math.round(v * 100)} sur 100` });
    let bas = 0;
    carte.classes.forEach((c, k) => {
      const haut = Math.min(c.seuil, 1);
      z.append(el("span", { style: `width:${(haut - bas) * 100}%${k ? `;background:rgb(${pal.classes[k].join(",")})` : ""}` }));
      bas = haut;
    });
    z.append(el("i", { style: `left:${Math.min(v, 1) * 100}%` }));
    return z;
  }

  function phaseSaison(e, s, jour, lat) {
    if (s >= 1) return "Pleine saison";
    if (s <= 0) return "Hors saison";
    // Avant ou après le milieu du plein de la saison (celle de l'an passé compte en janvier).
    const [, b, c] = datesSaison(e, jour.annee, lat, communs);
    const avant = jour.num < (b + c) / 2 && jour.num > datesSaison(e, jour.annee - 1, lat, communs)[3];
    return avant ? "Début de saison" : "Fin de saison";
  }

  // Ce qui retient l'indice : les facteurs sous 0,7, du plus bas au plus haut, deux au plus.
  function raison(e, r, cas, jour) {
    const p = r.parts;
    const [, p1] = e.pluie_mm;
    const [, s1, s2] = e.sol;
    const [jmin, jmax] = e.pluie_jours;
    const ph = fr1.format(cas.ph / 10);
    const habitat = !p ? [[r.habitat, `l'habitat de la zone (forêt, sol, altitude), ${r.habitat < 0.5 ? "peu" : "moyennement"} favorable`]] : [
      [p.essence, `la forêt (${leg.essences[cas.essence].toLowerCase()}), ${p.essence < 0.5 ? "peu" : "moyennement"} favorable`],
      [p.ouverte, "une forêt ouverte, au couvert clairsemé"],
      [p.sol, p.parLePh ? `le sol, pH ${ph} : ${cas.ph / 10 < e.ph[1] ? "trop acide" : "pas assez acide"}`
        : `la roche (${leg.roches[cas.roche].toLowerCase()})`],
      [p.altitude, p.plancher !== null && cas.altitude < p.plancher
        ? `l'altitude, trop basse (pleine dès ${fr.format(p.plancher)} m ici)`
        : p.altitude > 0 ? `l'altitude, près de son plafond (${fr.format(p.plafond)} m ici)`
          : "l'altitude, au-dessus de son plafond"],
      [p.pente, `la pente (${fr.format(cas.pente)}°)`]];
    const facteurs = [
      ...habitat,
      [r.saison, phaseSaison(e, r.saison, jour, cas.lat).toLowerCase()],
      [r.facteurs.pluie, `la pluie : ${fr.format(r.pluie)} mm entre ${jmax} et ${jmin} jours avant, ` +
        `il en faut ${fr.format(p1)} pour une pleine pousse`],
      [r.facteurs.sol, r.tSol < s1 ? `le sol, trop froid (${fr1.format(r.tSol)} °C sur 7 jours, il faut ${fr.format(s1)} °C)`
        : `le sol, trop chaud (${fr1.format(r.tSol)} °C sur 7 jours, au-delà de ${fr.format(s2)} °C)`],
      [r.facteurs.gel, `le gel (${r.gel} jour${r.gel > 1 ? "s" : ""} sur les 7 derniers)`],
    ].sort((a, b) => a[0] - b[0]);
    const limitent = facteurs.filter(([v]) => v < 0.7).slice(0, 2).map(([, t]) => t);
    if (limitent.length) return [el("strong", {}, "Ce qui limite : "), `${limitent.join(" ; ")}.`];
    if (r.indice >= carte.classes[2].seuil) return [el("strong", {}, "Tout est réuni : "),
      "forêt, sol, pluie et température conviennent."];
    return [el("strong", {}, "Rien ne bloque, "), `mais des facteurs moyens se cumulent : ${facteurs.slice(0, 2).map(([, t]) => t).join(" ; ")}.`];
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

  // --- Explorer les forêts ----------------------------------------------------------
  // Les critères du mode exploration, cochés dans le panneau ; « Partir de l'espèce » coche ce
  // que ses règles jugent favorable (affinité ≥ 0,8, plafond d'altitude à la latitude).
  function installerExploration() {
    const leg = carte.legendes;
    const cases = (zone, legende, cles) => $(zone).replaceChildren(...cles.map((k) =>
      el("label", { class: "case" }, el("input", { type: "checkbox", value: k, checked: "" }), legende[k])));
    cases("explorer-essences", leg.essences, Object.keys(leg.essences).filter((k) => k !== "0"));
    cases("explorer-roches", leg.roches, Object.keys(leg.roches));
    cases("explorer-orientations", leg.orientations, Object.keys(leg.orientations));
    const coches = (zone) => [...$(zone).querySelectorAll("input:checked")].map((x) => Number(x.value));
    const message = () => {
      $("explorer-message").textContent = etat.filtre && map.getZoom() < DETAIL
        ? "Rapprochez-vous : les forêts retenues s'affichent case par case, de près." : "";
    };
    function appliquer() {
      if ($("explorer-actif").checked && !modeFin()) {     // case par case : c'est la carte fine
        $("explorer-actif").checked = false;
        $("explorer-message").textContent = carte.fine
          ? "L'exploration montre les forêts case par case : elle demande la carte fine (mot de passe, plus haut)."
          : "L'exploration montre les forêts case par case : elle n'est pas disponible sur la carte publique.";
        return;
      }
      etat.filtre = $("explorer-actif").checked ? {
        essences: coches("explorer-essences"), roches: coches("explorer-roches"),
        orientations: coches("explorer-orientations"),
        altitude: [Number($("explorer-alt-min").value) || 0, Number($("explorer-alt-max").value) || 5000],
        publique: $("explorer-public").checked,
      } : null;
      message();
      calqueApercu.redraw();
      calqueDetail.redraw();
    }
    $("explorer").addEventListener("change", appliquer);
    map.on("zoomend", message);
    $("explorer-espece").addEventListener("click", () => {
      const e = especes[etat.espece];
      if (desPres(e.code)) {
        $("explorer-message").textContent = "L'exploration ne porte que sur les forêts : choisissez une espèce de forêt.";
        return;
      }
      const lat = deps[etat.departement]?.centre?.[0] ?? communs.latitude_ref;
      for (const x of $("explorer-essences").querySelectorAll("input")) x.checked = (e.essences[x.value] ?? 0) >= 0.8;
      for (const x of $("explorer-roches").querySelectorAll("input")) x.checked = (e.roches[x.value] ?? 0) >= 0.8;
      const monte = communs.hopkins_metres * (communs.latitude_ref - lat);
      $("explorer-alt-min").value = e.plancher[1] > 0 ? Math.max(0, Math.round(e.plancher[1] + monte)) : 0;
      $("explorer-alt-max").value = Math.round(e.altitude[0] + monte);
      $("explorer-actif").checked = true;
      appliquer();
    });
  }

  // Forêts publiques seulement : de près (la vue large ne distingue pas les forêts publiques).
  function installerPubliques() {
    const message = () => {
      $("publiques-message").textContent = etat.publiques && map.getZoom() < DETAIL ? "(de près seulement)" : "";
    };
    $("publiques").addEventListener("change", (ev) => {
      etat.publiques = ev.target.checked;
      message();
      calqueDetail.redraw();
    });
    map.on("zoomend", message);
  }

  // Les onglets du panneau : un seul visible ; flèches gauche et droite d'un onglet à l'autre.
  const ONGLETS = ["ici", "departement", "espece", "outils"];
  function onglet(nom) {
    for (const o of ONGLETS) {
      const choisi = o === nom;
      $(`tab-${o}`).setAttribute("aria-selected", String(choisi));
      $(`tab-${o}`).tabIndex = choisi ? 0 : -1;
      $(`onglet-${o}`).hidden = !choisi;
    }
  }
  for (const o of ONGLETS) {
    $(`tab-${o}`).addEventListener("click", () => onglet(o));
    $(`tab-${o}`).addEventListener("keydown", (ev) => {
      const pas = { ArrowRight: 1, ArrowLeft: -1 }[ev.key];
      if (!pas) return;
      const suivant = ONGLETS[(ONGLETS.indexOf(o) + pas + ONGLETS.length) % ONGLETS.length];
      onglet(suivant);
      $(`tab-${suivant}`).focus();
    });
  }

  function tout() {
    choixJours();
    panneau();
    queChercherIci();
    afficherCase();
    if (feuille.etat() === "bas") feuille.poser("bas");      // les choix ont pu changer de hauteur
    rafraichirCalques();
    coins.rafraichir();
  }

  legende();
  installerFine();
  installerExploration();
  installerPubliques();
  antipoison();
  resume = await resumes(etat.departement);
  if (!lire(CLE_ESPECE) && !especes[demande.get("espece")]) {   // première visite : la mieux placée
    const meilleure = carte.especes.filter((e) => !desPres(e.code)).sort((a, b) =>
      (resume[b.code]?.[jourDepart]?.niveau ?? 0) - (resume[a.code]?.[jourDepart]?.niveau ?? 0))[0];
    etat.espece = meilleure.code;
  }
  if (depDemande) onglet("departement");
  tout();
  // Première visite : la présentation, puis la demande de position (elle attend la fermeture).
  const guide = installerGuide($("guide"), { etroit: feuille.etroit });
  $("revoir-guide").addEventListener("click", guide.ouvrir);
  if (guide.premiereVisite()) {
    $("guide").addEventListener("close", positionOuverture, { once: true });
    guide.ouvrir();
  } else {
    positionOuverture();
  }
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

function jourEnMots(num) {
  const d = new Date(Math.round(num) * 864e5);
  return `${d.getUTCDate() === 1 ? "1er" : d.getUTCDate()} ${MOIS[d.getUTCMonth()]}`;
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

// Installer l'appli : le bouton du navigateur quand il en propose un (Chrome, Android), la marche
// à suivre sur iPhone, rien une fois installée.
function proposerInstallation() {
  const zone = $("installer");
  if (matchMedia("(display-mode: standalone)").matches || navigator.standalone) return;
  const pourquoi = " : sur l'écran d'accueil, en plein écran, utilisable sans réseau en forêt.";
  window.addEventListener("beforeinstallprompt", (ev) => {
    ev.preventDefault();
    zone.replaceChildren(el("button", { type: "button", class: "lien", onclick: async () => {
      await ev.prompt();
      zone.hidden = true;
    } }, "Installer l'application"), pourquoi);
    zone.hidden = false;
  });
  if (/iPhone|iPad/.test(navigator.userAgent)) {
    zone.textContent = "Sur iPhone : bouton Partager, puis « Sur l'écran d'accueil »" + pourquoi +
      " Safari n'y efface plus vos coins.";
    zone.hidden = false;
  }
}

// L'appli hors ligne (sw.js) : la carte s'ouvre ensuite sans réseau, avec les dernières données.
navigator.serviceWorker?.register("sw.js").catch((err) => console.error(err));
proposerInstallation();

demarrer().catch((err) => {
  console.error(err);
  $("verdict-titre").textContent = "La carte n'a pas pu se charger.";
});
