// Carte de l'indice de pousse, à la résolution de calcul (cases de 50 m).
// Lit data/carte.json, data/especes.json et des images PNG où chaque pixel est une case
// (codage des canaux : champi/export.py). Le calque est dessiné tuile par tuile, à l'échelle
// de l'écran : cases nettes et hachures fines à tous les zooms.

const R = 6378137;
const MONDE = 2 * Math.PI * R;
const CLE_ESPECE = "champi-espece"; // seule donnée gardée dans le navigateur (voir a-propos.html)
const NIVEAU_COURT = ["hors saison", "défavorable", "possible", "par endroits", "bon"];
const OPACITE = 175;                // sur 255 : le fond de carte reste lisible
const EN_MEMOIRE = 8;               // grilles d'indice gardées (≈ 3 Mo chacune)

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
function versLatLon(x, y) {
  return [(2 * Math.atan(Math.exp(y / R)) - Math.PI / 2) * 180 / Math.PI, x / R * 180 / Math.PI];
}

function lireStockage() {
  try { return localStorage.getItem(CLE_ESPECE); } catch { return null; }
}
function ecrireStockage(v) {
  try { localStorage.setItem(CLE_ESPECE, v); } catch { /* navigation privée : sans conséquence */ }
}

// Décode un PNG en tableau d'octets RVBA (canvas : les PNG sans profil de couleur restent bruts).
async function pixels(url) {
  const img = new Image();
  img.src = url;
  await img.decode();
  const c = document.createElement("canvas");
  c.width = img.width;
  c.height = img.height;
  const ctx = c.getContext("2d", { willReadFrequently: true });
  ctx.drawImage(img, 0, 0);
  return { l: img.width, h: img.height, d: ctx.getImageData(0, 0, img.width, img.height).data };
}

// Un PNG en niveaux de gris → un octet par case.
async function canal(url) {
  const px = await pixels(url);
  const v = new Uint8Array(px.l * px.h);
  for (let i = 0; i < v.length; i++) v[i] = px.d[i * 4];
  return v;
}

// Charge une seule fois, à la demande.
function paresseux(charger) {
  const memo = new Map();
  return (cle) => {
    if (!memo.has(cle)) memo.set(cle, charger(cle).catch((e) => { memo.delete(cle); throw e; }));
    return memo.get(cle);
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
  const g = carte.grille;
  const gz = carte.grille_zone;
  const codes = carte.codes;
  const leg = carte.legendes;
  const pal = couleurs();

  // Couleur de chaque code d'indice (0-255), calculée une fois : RVBA à plat.
  const TABLE = new Uint8ClampedArray(256 * 4);
  for (let code = 0; code <= carte.echelle; code++) {
    const k = classeDe(code / carte.echelle, carte.classes);
    if (k === 0) continue;
    TABLE.set([...pal.classes[k], OPACITE], code * 4);
  }

  // Données chargées à la demande : seul l'indice affiché part d'emblée.
  const fixes = paresseux((nom) => pixels(`data/${nom}.png`));
  const sol = paresseux((k) => canal(`data/sol_${k}.png`));
  const pluie = paresseux((cle) => canal(`data/pluie/${cle}.png`));
  const indices = new Map();
  function indice(cle) {
    if (!indices.has(cle)) {
      indices.set(cle, canal(`data/indice/${cle}.png`).catch((e) => { indices.delete(cle); throw e; }));
      if (indices.size > EN_MEMOIRE) indices.delete(indices.keys().next().value);
    }
    return indices.get(cle);
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

  // --- État -----------------------------------------------------------------------
  const resumes = carte.resumes;
  const meilleure = carte.especes.slice().sort((a, b) =>
    resumes[b.code][jourDepart].niveau - resumes[a.code][jourDepart].niveau)[0].code;
  const memo = lireStockage();
  const etat = { espece: especes[memo] ? memo : meilleure, jour: jourDepart };

  // --- Carte ----------------------------------------------------------------------
  const b = carte.bornes;
  const bornes = L.latLngBounds([b.sud, b.ouest], [b.nord, b.est]);
  const map = L.map("carte", { minZoom: 8, maxZoom: 18, maxBounds: bornes.pad(0.3), zoomSnap: 0.5 });
  map.fitBounds(bornes);
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
  map.attributionControl.addAttribution("Indice : météo Open-Meteo, forêts et relief IGN, roches BRGM");

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

  let courant = null;   // grille d'indice affichée (un octet par case)

  // Chaque pixel d'écran va chercher sa case : x, y Mercator → colonne, ligne de la grille.
  const Calque = L.GridLayer.extend({
    createTile(coords) {
      const tuile = document.createElement("canvas");
      tuile.width = tuile.height = 256;
      if (!courant) return tuile;
      const n = 256 * 2 ** coords.z;
      const cols = new Int32Array(256);
      const lignes = new Int32Array(256);
      let visible = false;
      for (let i = 0; i < 256; i++) {
        const x = ((coords.x * 256 + i + 0.5) / n) * MONDE - MONDE / 2;
        const y = MONDE / 2 - ((coords.y * 256 + i + 0.5) / n) * MONDE;
        cols[i] = Math.floor((x - g.x0) / g.pas);
        lignes[i] = Math.floor((g.y1 - y) / g.pas);
        if (cols[i] >= 0 && cols[i] < g.nx) visible = true;
      }
      if (!visible) return tuile;
      const ctx = tuile.getContext("2d");
      const img = ctx.createImageData(256, 256);
      const o = img.data;
      for (let j = 0; j < 256; j++) {
        const lig = lignes[j];
        if (lig < 0 || lig >= g.ny) continue;
        const base = lig * g.nx;
        for (let i = 0; i < 256; i++) {
          const col = cols[i];
          if (col < 0 || col >= g.nx) continue;
          const code = courant[base + col];
          const p = (j * 256 + i) * 4;
          if (code === codes.protege) {   // hachures : « réglementation propre », jamais un gris plein
            if ((coords.x * 256 + i + coords.y * 256 + j) % 7 < 2) {
              o[p] = pal.hachure[0]; o[p + 1] = pal.hachure[1]; o[p + 2] = pal.hachure[2]; o[p + 3] = 150;
            }
            continue;
          }
          const t = code * 4;
          o[p] = TABLE[t]; o[p + 1] = TABLE[t + 1]; o[p + 2] = TABLE[t + 2]; o[p + 3] = TABLE[t + 3];
        }
      }
      ctx.putImageData(img, 0, 0);
      return tuile;
    },
  });
  const calque = new Calque({ pane: "overlayPane", updateWhenZooming: false, keepBuffer: 1 }).addTo(map);

  async function rafraichirCalque() {
    const demande = `${etat.espece}_${etat.jour}`;
    const grille = await indice(demande);
    if (demande !== `${etat.espece}_${etat.jour}`) return; // l'utilisateur a déjà changé d'avis
    courant = grille;
    calque.redraw();
    // Le jour suivant se prépare en arrière-plan : le changement de jour sera immédiat.
    if (etat.jour + 1 < carte.jours.length) indice(`${etat.espece}_${etat.jour + 1}`).catch(() => {});
  }

  // --- Panneau --------------------------------------------------------------------
  function choixEspeces() {
    const zone = $("choix-espece");
    zone.replaceChildren();
    for (const e of carte.especes) {
      const r = resumes[e.code][etat.jour];
      const input = el("input", { type: "radio", name: "espece", value: e.code });
      input.checked = e.code === etat.espece;
      input.addEventListener("change", () => { etat.espece = e.code; ecrireStockage(e.code); tout(); });
      zone.append(el("label", {}, input, e.nom, el("span", { class: "niv" }, NIVEAU_COURT[r.niveau])));
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
    const [, s1, s2] = e.saison;
    const corps = [
      el("p", {}, e.description),
      el("p", {}, el("strong", {}, "Saison : "), `surtout du ${dateCourte(s1)} au ${dateCourte(s2)}. `,
        el("strong", {}, "Milieu : "), e.habitat_texte),
    ];
    if (e.confusions) corps.push(el("p", { class: "confusions" }, el("strong", {}, "Confusions possibles : "), e.confusions));
    corps.push(el("p", { class: "muet" }, "Ce portrait ne suffit jamais pour identifier un champignon."));
    $("fiche").replaceChildren(
      el("details", { open: "" },
        el("summary", {}, el("strong", {}, e.nom), " ", el("span", { class: "latin" }, e.latin)),
        ...corps));
  }

  function verdict() {
    const r = resumes[etat.espece][etat.jour];
    const e = especes[etat.espece];
    $("verdict-jour").textContent = `${e.nom}, ${carte.jours[etat.jour].libelle}`;
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
    if (!r.communes.length || r.niveau === 0) {
      ul.append(el("li", { class: "muet" }, "Aucune commune ne se détache."));
    }
    for (const c of r.niveau === 0 ? [] : r.communes) {
      ul.append(el("li", {}, el("button", { type: "button", onclick: () => allerA(c.nom) },
        c.nom, el("span", { class: "cl" }, carte.classes[c.classe].nom))));
    }
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
  }

  async function allerA(nomCommune) {
    const idx = leg.communes.indexOf(nomCommune) + 1;
    const lieux = await fixes("lieux");
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    for (let y = 0; y < lieux.h; y++) {
      for (let x = 0; x < lieux.l; x++) {
        const i = (y * lieux.l + x) * 4;
        if (lieux.d[i] + 256 * lieux.d[i + 1] === idx) {
          if (x < x0) x0 = x;
          if (x > x1) x1 = x;
          if (y < y0) y0 = y;
          if (y > y1) y1 = y;
        }
      }
    }
    if (x0 === Infinity) return;
    const so = versLatLon(g.x0 + x0 * g.pas, g.y1 - (y1 + 1) * g.pas);
    const ne = versLatLon(g.x0 + (x1 + 1) * g.pas, g.y1 - y0 * g.pas);
    map.fitBounds([so, ne], { maxZoom: 15 });
    if (window.matchMedia("(max-width: 820px)").matches) $("carte").scrollIntoView({ behavior: "smooth" });
  }

  // --- Fenêtre d'une case ---------------------------------------------------------
  map.on("click", async (ev) => {
    if (!courant) return;
    const [x, y] = versMerc(ev.latlng.lat, ev.latlng.lng);
    const col = Math.floor((x - g.x0) / g.pas);
    const lig = Math.floor((g.y1 - y) / g.pas);
    if (col < 0 || lig < 0 || col >= g.nx || lig >= g.ny) return;
    const i = lig * g.nx + col;
    const code = courant[i];
    if (code === codes.hors_departement) return;
    const izone = Math.floor(lig / (gz.pas / g.pas)) * gz.nx + Math.floor(col / (gz.pas / g.pas));
    const popup = L.popup({ maxWidth: 330 }).setLatLng(ev.latlng).setContent("Chargement…").openOn(map);
    try {
      const cle = `${etat.espece}_${etat.jour}`;
      const [attributs, lieux, sols, pluies] = await Promise.all([
        fixes("attributs"), fixes("lieux"), sol(etat.jour), pluie(cle)]);
      popup.setContent(fenetre(code, i, attributs, lieux, sols[i], pluies[izone], ev.latlng));
    } catch (err) {
      console.error(err);
      popup.setContent("Les détails de cette case n'ont pas pu se charger.");
    }
  });

  function fenetre(code, i, attributs, lieux, codeSol, pluieZone, ll) {
    const e = especes[etat.espece];
    const q = i * 4;
    const idxCommune = lieux.d[q] + 256 * lieux.d[q + 1];
    const commune = leg.communes[idxCommune - 1] || "Hors commune";
    const div = el("div");
    div.append(el("h4", {}, commune));
    if (code === codes.protege) {
      const z = leg.protections[lieux.d[q + 2] - 1];
      div.append(el("p", {}, `${z ? `${z.nature} « ${z.nom} »` : "Zone protégée"}. Ces espaces ont leur propre ` +
        "réglementation, souvent plus stricte sur la cueillette : renseignez-vous avant d'y ramasser quoi que ce soit. " +
        "Le site n'y calcule pas d'indice."));
      return div;
    }
    const ess = attributs.d[q + 1] & 15;
    const alt = attributs.d[q] * 20;
    if (code === codes.hors_foret) {
      div.append(el("p", {}, `Hors forêt (≈ ${fr.format(alt)} m) : pas d'indice.`));
      return div;
    }
    const v = code / carte.echelle;
    const k = classeDe(v, carte.classes);
    const pastille = k > 0 ? el("span", { class: "pastille", style: `background:rgb(${pal.classes[k].join(",")})` })
      : el("span", { class: "pastille vide" });
    div.append(el("div", { class: "pop-indice" }, pastille,
      `${e.nom} : ${carte.classes[k].nom.toLowerCase()} (${fr2.format(v)})`));
    div.append(el("div", { class: "muet" }, carte.jours[etat.jour].libelle));

    const publique = (attributs.d[q + 1] >> 4) & 1;
    const ouverte = (attributs.d[q + 1] >> 5) & 1;
    const roche = attributs.d[q + 2] & 3;
    const orient = attributs.d[q + 2] >> 2;
    const [p0, p1] = e.pluie_mm;
    const [, s1, s2] = e.sol;
    const mot = (a) => (a >= 0.8 ? "élevée" : a >= 0.5 ? "moyenne" : "faible");

    const dl = el("dl");
    const ligne = (t, d, cls) => { dl.append(el("dt", {}, t), el("dd", cls ? { class: cls } : {}, d)); };
    ligne("Forêt", `${leg.essences[ess]}${ouverte ? " (ouverte)" : ""}`);
    ligne("Affinité", `${mot(e.essences[ess] ?? 0)} pour cette forêt, ${mot(e.roches[roche] ?? 0)} pour la roche`);
    ligne("Roche", leg.roches[roche]);
    ligne("Altitude", `≈ ${fr.format(alt)} m`);
    ligne("Exposition", leg.orientations[orient]);
    ligne("Statut", publique ? "forêt publique (régime forestier)" : "forêt probablement privée");
    const [jmin, jmax] = e.pluie_jours;
    if (pluieZone !== 255) {
      ligne(`Pluie ${jmin}–${jmax} j avant`,
        `${fr.format(pluieZone)} mm ${pluieZone >= p1 ? "✓" : pluieZone < p0 ? "✗ trop peu" : "– un peu juste"}`,
        pluieZone >= p1 ? "ok" : pluieZone < p0 ? "ko" : "");
    }
    if (codeSol !== 255) {
      const t = codeSol / 5 - 10;
      ligne("Sol (7 jours)", `${fr1.format(t)} °C ${t < s1 ? "✗ trop froid" : t > s2 ? "✗ trop chaud" : "✓"}`,
        t < s1 || t > s2 ? "ko" : "ok");
    }
    div.append(dl);
    div.append(el("p", { class: "muet" },
      `Case de 50 m ; pluie moyenne sur 250 m. Pleine pousse au-delà de ${fr.format(p1)} mm, ` +
      `sol entre ${fr.format(s1)} et ${fr.format(s2)} °C.`));
    div.append(el("a", {
      href: `https://www.geoportail.gouv.fr/carte?c=${ll.lng.toFixed(5)},${ll.lat.toFixed(5)}&z=16&permalink=yes`,
      target: "_blank", rel: "noopener",
    }, "Voir le lieu sur le Géoportail (IGN)"));
    return div;
  }

  function tout() {
    choixEspeces();
    choixJours();
    fiche();
    verdict();
    rafraichirCalque();
  }

  legende();
  tout();
  const genere = new Date(carte.genere_le);
  $("maj").textContent = `Calculée le ${genere.toLocaleString("fr-FR", { dateStyle: "long", timeStyle: "short", timeZone: "Europe/Paris" })}.`;
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
