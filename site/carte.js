// Carte de l'indice de pousse. Lit data/carte.json, data/especes.json et les images PNG
// où chaque pixel est une zone de 250 m (voir champi/export.py pour le codage des canaux).

const R = 6378137;
const SUREchantillon = 4;           // pixels d'écran par zone dans l'image de la carte
const CLE_ESPECE = "champi-espece"; // seule donnée gardée dans le navigateur (voir a-propos.html)
const NIVEAU_COURT = ["hors saison", "défavorable", "possible", "par endroits", "bon"];

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
  const codes = carte.codes;
  const leg = carte.legendes;
  const pal = couleurs();
  const [attributs, lieux] = await Promise.all([pixels("data/attributs.png"), pixels("data/lieux.png")]);
  const cache = new Map();

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
  const map = L.map("carte", { minZoom: 8, maxZoom: 17, maxBounds: bornes.pad(0.3), zoomSnap: 0.5 });
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

  let calque = null;
  let urlCalque = null;
  let courant = null;

  async function donneesDuJour() {
    const cle = `${etat.espece}_${etat.jour}`;
    if (!cache.has(cle)) cache.set(cle, pixels(`data/indice/${cle}.png`));
    return cache.get(cle);
  }

  function image(px) {
    const f = SUREchantillon;
    const c = document.createElement("canvas");
    c.width = px.l * f;
    c.height = px.h * f;
    const ctx = c.getContext("2d");
    const out = ctx.createImageData(c.width, c.height);
    const o = out.data;
    for (let y = 0; y < px.h; y++) {
      for (let x = 0; x < px.l; x++) {
        const code = px.d[(y * px.l + x) * 4];
        if (code === codes.hors_departement || code === codes.hors_foret) continue;
        let rgb = null;
        let alpha = 165;
        if (code !== codes.protege) {
          const k = classeDe(code / carte.echelle, carte.classes);
          if (k === 0) continue;
          rgb = pal.classes[k];
        }
        for (let sy = 0; sy < f; sy++) {
          for (let sx = 0; sx < f; sx++) {
            const X = x * f + sx;
            const Y = y * f + sy;
            let c3 = rgb;
            if (code === codes.protege) {   // hachures : « réglementation propre », jamais un gris plein
              if ((X + Y) % 5 !== 0) continue;
              c3 = pal.hachure;
              alpha = 170;
            }
            const i = (Y * c.width + X) * 4;
            o[i] = c3[0]; o[i + 1] = c3[1]; o[i + 2] = c3[2]; o[i + 3] = alpha;
          }
        }
      }
    }
    ctx.putImageData(out, 0, 0);
    return new Promise((ok) => c.toBlob(ok, "image/png"));
  }

  async function rafraichirCalque() {
    const demande = `${etat.espece}_${etat.jour}`;
    const px = await donneesDuJour();
    if (demande !== `${etat.espece}_${etat.jour}`) return; // l'utilisateur a déjà changé d'avis
    courant = px;
    const blob = await image(px);
    const url = URL.createObjectURL(blob);
    if (calque) calque.setUrl(url);
    else calque = L.imageOverlay(url, bornes, { className: "indice-image", interactive: false }).addTo(map);
    if (urlCalque) URL.revokeObjectURL(urlCalque);
    urlCalque = url;
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

  function verdict() {
    const r = resumes[etat.espece][etat.jour];
    const e = especes[etat.espece];
    $("verdict-jour").textContent = `${e.nom}, ${carte.jours[etat.jour].libelle}`;
    $("verdict-titre").textContent = r.verdict;
    $("verdict-texte").replaceChildren(...r.phrases.map((p) => el("p", {}, p)));

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

  function allerA(nomCommune) {
    const idx = leg.communes.indexOf(nomCommune) + 1;
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    for (let y = 0; y < lieux.h; y++) {
      for (let x = 0; x < lieux.l; x++) {
        const i = (y * lieux.l + x) * 4;
        if (lieux.d[i] + 256 * lieux.d[i + 1] === idx) {
          x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y);
        }
      }
    }
    if (x0 === Infinity) return;
    const so = versLatLon(g.x0 + x0 * g.pas, g.y1 - (y1 + 1) * g.pas);
    const ne = versLatLon(g.x0 + (x1 + 1) * g.pas, g.y1 - y0 * g.pas);
    map.fitBounds([so, ne], { maxZoom: 14 });
    if (window.matchMedia("(max-width: 820px)").matches) $("carte").scrollIntoView({ behavior: "smooth" });
  }

  // --- Fenêtre d'une zone --------------------------------------------------------
  map.on("click", (ev) => {
    if (!courant) return;
    const [x, y] = versMerc(ev.latlng.lat, ev.latlng.lng);
    const col = Math.floor((x - g.x0) / g.pas);
    const lig = Math.floor((g.y1 - y) / g.pas);
    if (col < 0 || lig < 0 || col >= courant.l || lig >= courant.h) return;
    const i = (lig * courant.l + col) * 4;
    const code = courant.d[i];
    if (code === codes.hors_departement) return;
    const contenu = fenetre(code, i, ev.latlng);
    L.popup({ maxWidth: 320 }).setLatLng(ev.latlng).setContent(contenu).openOn(map);
  });

  function fenetre(code, i, ll) {
    const e = especes[etat.espece];
    const idxCommune = lieux.d[i] + 256 * lieux.d[i + 1];
    const commune = leg.communes[idxCommune - 1] || "Hors commune";
    const div = el("div");
    div.append(el("h4", {}, commune));
    if (code === codes.protege) {
      const z = leg.protections[lieux.d[i + 2] - 1];
      div.append(el("p", {}, `${z ? `${z.nature} « ${z.nom} »` : "Zone protégée"}. Ces espaces ont leur propre ` +
        "réglementation, souvent plus stricte sur la cueillette : renseignez-vous avant d'y ramasser quoi que ce soit. " +
        "Le site n'y calcule pas d'indice."));
      return div;
    }
    if (code === codes.hors_foret) {
      div.append(el("p", {}, "Peu ou pas de forêt dans cette zone de 250 m : pas d'indice."));
      return div;
    }
    const v = code / carte.echelle;
    const k = classeDe(v, carte.classes);
    const pastille = k > 0 ? el("span", { class: "pastille", style: `background:rgb(${pal.classes[k].join(",")})` })
      : el("span", { class: "pastille vide" });
    div.append(el("div", { class: "pop-indice" }, pastille,
      `${e.nom} : ${carte.classes[k].nom.toLowerCase()} (${fr2.format(v)})`));
    div.append(el("div", { class: "muet" }, carte.jours[etat.jour].libelle));

    const ess = attributs.d[i + 1] & 15;
    const publique = (attributs.d[i + 1] >> 4) & 1;
    const ouverte = (attributs.d[i + 1] >> 5) & 1;
    const roche = attributs.d[i + 2] & 3;
    const orient = attributs.d[i + 2] >> 2;
    const alt = attributs.d[i] * 20;
    const pluie = courant.d[i + 1];
    const sol = courant.d[i + 2] / 5 - 10;
    const [p0, p1] = e.pluie_mm;
    const [, s1, s2] = e.sol;
    const affinite = e.essences[ess] ?? 0;
    const mot = (a) => (a >= 0.8 ? "élevée" : a >= 0.5 ? "moyenne" : "faible");

    const dl = el("dl");
    const ligne = (t, d, cls) => { dl.append(el("dt", {}, t), el("dd", cls ? { class: cls } : {}, d)); };
    ligne("Forêt", `${leg.essences[ess]}${ouverte ? " (ouverte)" : ""}`);
    ligne("Affinité", `${mot(affinite)} pour cette forêt, ${mot(e.roches[roche] ?? 0)} pour la roche`);
    ligne("Roche", `${leg.roches[roche]}`);
    ligne("Altitude", `≈ ${fr.format(alt)} m`);
    ligne("Exposition", leg.orientations[orient]);
    ligne("Statut", publique ? "forêt publique (régime forestier)" : "forêt probablement privée");
    const [jmin, jmax] = e.pluie_jours;
    ligne(`Pluie ${jmin}–${jmax} j avant`, `${fr.format(pluie)} mm ${pluie >= p1 ? "✓" : pluie < p0 ? "✗ trop peu" : "– un peu juste"}`,
      pluie >= p1 ? "ok" : pluie < p0 ? "ko" : "");
    ligne("Sol (7 jours)", `${fr1.format(sol)} °C ${sol < s1 ? "✗ trop froid" : sol > s2 ? "✗ trop chaud" : "✓"}`,
      sol < s1 || sol > s2 ? "ko" : "ok");
    div.append(dl);
    div.append(el("p", { class: "muet" },
      "Forêt, roche et exposition dominantes de la zone de 250 m. Pleine pousse au-delà de " +
      `${fr.format(p1)} mm, sol entre ${fr.format(s1)} et ${fr.format(s2)} °C.`));
    div.append(el("a", {
      href: `https://www.geoportail.gouv.fr/carte?c=${ll.lng.toFixed(5)},${ll.lat.toFixed(5)}&z=15&permalink=yes`,
      target: "_blank", rel: "noopener",
    }, "Voir le lieu sur le Géoportail (IGN)"));
    return div;
  }

  function tout() {
    choixEspeces();
    choixJours();
    verdict();
    rafraichirCalque();
  }

  legende();
  tout();
  const genere = new Date(carte.genere_le);
  $("maj").textContent = `Calculée le ${genere.toLocaleString("fr-FR", { dateStyle: "long", timeStyle: "short", timeZone: "Europe/Paris" })}.`;
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
