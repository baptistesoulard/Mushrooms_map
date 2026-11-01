// Le calcul de l'indice dans le navigateur : la traduction exacte de champi/modele.py et de
// la voie rapide de champi/export.py (Calcul.entrees). Les seuils viennent de especes.json,
// jamais d'ici. tests/test_modele_js.py vérifie l'égalité avec Python sur des cas tirés au sort.

export function trapeze(x, a, b, c, d) {
  const m = Math.min(Math.max((x - a) / Math.max(b - a, 1e-6), 0), 1);
  const s = Math.min(Math.max((d - x) / Math.max(d - c, 1e-6), 0), 1);
  return Math.min(m, s);
}

export function montee(x, a, b) {
  return Math.min(Math.max((x - a) / Math.max(b - a, 1e-6), 0), 1);
}

// Jours depuis le 1er janvier 1970 (UTC) : seules les différences comptent.
export function jourNum(annee, mois, jour) {
  return Date.UTC(annee, mois - 1, jour) / 86400000;
}

export function decalageJours(mmjj, lat, c) {
  const mois = Number(mmjj.slice(0, 2));
  const sens = mois <= 6 ? 1 : mois >= 8 ? -1 : 0;
  return sens * c.hopkins_jours * (lat - c.latitude_ref);
}

export function datesSaison(esp, annee, lat, c) {
  return esp.saison.map((s) => jourNum(annee, Number(s.slice(0, 2)), Number(s.slice(3, 5))) + decalageJours(s, lat, c));
}

// `jour` : { annee, num } ; la saison de l'année précédente compte aussi (débord sur janvier).
export function facteurSaison(esp, jour, lat, c) {
  let f = 0;
  for (const annee of [jour.annee - 1, jour.annee]) {
    const [a, b, cc, d] = datesSaison(esp, annee, lat, c).map((v) => v - jour.num);
    f = Math.max(f, trapeze(0, a, b, cc, d));
  }
  return f;
}

export function plafondAltitude(esp, lat, c) {
  const monte = c.hopkins_metres * (c.latitude_ref - lat);
  return [esp.altitude[0] + monte, esp.altitude[1] + monte];
}

export function facteurPente(pente, c) {
  const [debut, fin, plancher] = c.pente;
  const baisse = (pente - debut) / (fin - debut) * (1 - plancher);
  return Math.min(Math.max(1 - baisse, plancher), 1);
}

// pH du sol (× 10, 0 = inconnu) : trapèze relevé d'un plancher.
export function facteurPh(esp, ph) {
  const [a, b, cc, d] = esp.ph;
  return esp.ph_plancher + (1 - esp.ph_plancher) * trapeze(ph / 10, a, b, cc, d);
}

// Pour une espèce qui le demande (esp.sol_ph), le pH remplace la roche là où il est connu.
export function facteurHabitat(esp, essence, ouverte, roche, altitude, pente, lat, c, ph = 0) {
  const sol = esp.sol_ph && ph > 0 ? facteurPh(esp, ph) : (esp.roches[roche] ?? 0);
  let f = (esp.essences[essence] ?? 0) * sol;
  const [plein, nul] = plafondAltitude(esp, lat, c);
  f *= Math.min(Math.max((nul - altitude) / (nul - plein), 0), 1);
  f *= facteurPente(pente, c);
  return ouverte ? f * c.foret_ouverte : f;
}

export function pluieEfficace(pluie, ensoleillement, c) {
  return pluie * (1 - c.secheresse_sud * ensoleillement);
}

export function temperatureLocale(tMer, altitude, gradient, ensoleillement = 0, soleil = 0) {
  return tMer - gradient * altitude + soleil * ensoleillement;
}

export function facteursMeteo(esp, pluie, tSol, gel) {
  return {
    pluie: montee(pluie, ...esp.pluie_mm),
    sol: trapeze(tSol, ...esp.sol),
    gel: Math.pow(esp.gel, gel),
  };
}

// Interpolation bilinéaire sur une grille régulière (lat et lon croissantes), comme
// champi.meteo.Interpolateur : renvoie une fonction champ → valeur au point.
export function interpolateur(lats, lons, lat, lon) {
  const fi = (lat - lats[0]) / (lats[1] - lats[0]);
  const fj = (lon - lons[0]) / (lons[1] - lons[0]);
  const i0 = Math.min(Math.max(Math.floor(fi), 0), lats.length - 2);
  const j0 = Math.min(Math.max(Math.floor(fj), 0), lons.length - 2);
  const wi = Math.min(Math.max(fi - i0, 0), 1);
  const wj = Math.min(Math.max(fj - j0, 0), 1);
  const n = lons.length;
  const p00 = i0 * n + j0, p10 = p00 + n, p01 = p00 + 1, p11 = p10 + 1;
  return (champ) => (champ[p00] * (1 - wi) + champ[p10] * wi) * (1 - wj)
                  + (champ[p01] * (1 - wi) + champ[p11] * wi) * wj;
}

// --- Un bloc entier (la carte) ---------------------------------------------------
// Même calcul qu'`evaluer`, organisé pour des centaines de milliers de cases : les poids
// d'interpolation se calculent une fois par bloc, le gel une fois par jour.

// cases : tableaux de même longueur (lat, lon, altitude, ensoleillement, pente, essence,
// ouverte, roche, et ph s'il est connu) ; meteo : { lats, lons, champ(nom) }.
export function preparer(cases, meteo) {
  const n = cases.lat.length;
  const p00 = new Int32Array(n), wi = new Float64Array(n), wj = new Float64Array(n);
  const { lats, lons } = meteo;
  const nl = lons.length;
  for (let i = 0; i < n; i++) {
    const fi = (cases.lat[i] - lats[0]) / (lats[1] - lats[0]);
    const fj = (cases.lon[i] - lons[0]) / (lons[1] - lons[0]);
    const i0 = Math.min(Math.max(Math.floor(fi), 0), lats.length - 2);
    const j0 = Math.min(Math.max(Math.floor(fj), 0), lons.length - 2);
    p00[i] = i0 * nl + j0;
    wi[i] = Math.min(Math.max(fi - i0, 0), 1);
    wj[i] = Math.min(Math.max(fj - j0, 0), 1);
  }
  return { cases, n, nl, p00, wi, wj, gel: new Map() };
}

function interpoler(prep, champ) {
  const { n, nl, p00, wi, wj } = prep;
  const v = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    const a = p00[i], b = a + nl;
    v[i] = (champ[a] * (1 - wi[i]) + champ[b] * wi[i]) * (1 - wj[i])
         + (champ[a + 1] * (1 - wi[i]) + champ[b + 1] * wi[i]) * wj[i];
  }
  return v;
}

function gele(prep, meteo, d, c) {
  if (!prep.gel.has(d)) {
    const t = interpoler(prep, meteo.champ(`tmin_${d}`));
    const g = new Uint8Array(prep.n);
    for (let i = 0; i < prep.n; i++) g[i] = temperatureLocale(t[i], prep.cases.altitude[i], c.gradient_air) < c.gel_seuil ? 1 : 0;
    prep.gel.set(d, g);
  }
  return prep.gel.get(d);
}

// Indice de chaque case du bloc pour une espèce et un jour.
export function indices(esp, prep, meteo, jour, c) {
  const k = prep.cases;
  const [jmin, jmax] = esp.pluie_jours;
  const pluie = interpoler(prep, meteo.champ(`pluie_${jmin}_${jmax}_${jour.k}`));
  const tsol = interpoler(prep, meteo.champ(`tsol_${jour.k}`));
  const geles = [];
  for (let d = jour.k - 6; d <= jour.k; d++) geles.push(gele(prep, meteo, d, c));
  const saisons = new Map();      // la saison ne dépend que de la latitude
  const sortie = new Float32Array(prep.n);
  for (let i = 0; i < prep.n; i++) {
    const h = facteurHabitat(esp, k.essence[i], k.ouverte[i], k.roche[i], k.altitude[i], k.pente[i], k.lat[i], c,
                             k.ph ? k.ph[i] : 0);
    if (h === 0) continue;
    let s = saisons.get(k.lat[i]);
    if (s === undefined) { s = facteurSaison(esp, jour, k.lat[i], c); saisons.set(k.lat[i], s); }
    if (s === 0) continue;
    let gel = 0;
    for (const g of geles) gel += g[i];
    const f = facteursMeteo(esp, pluieEfficace(pluie[i], k.ensoleillement[i], c),
      temperatureLocale(tsol[i], k.altitude[i], c.gradient_sol, k.ensoleillement[i], c.soleil_sol), gel);
    sortie[i] = h * s * f.pluie * f.sol * f.gel;
  }
  return sortie;
}

// Une case : ses facteurs et son indice, pour l'espèce et le jour donnés.
//   cas : { essence, ouverte, roche, altitude, pente, ensoleillement, lat, lon, ph }
//   meteo : { lats, lons, champ(nom) → Float32Array } (sommes et moyennes déjà faites aux points)
//   jour : { annee, num, k } (k : rang du jour dans les champs)
export function evaluer(esp, cas, meteo, jour, c) {
  const habitat = facteurHabitat(esp, cas.essence, cas.ouverte, cas.roche, cas.altitude, cas.pente, cas.lat, c,
                                 cas.ph ?? 0);
  const saison = facteurSaison(esp, jour, cas.lat, c);
  const it = interpolateur(meteo.lats, meteo.lons, cas.lat, cas.lon);
  const [jmin, jmax] = esp.pluie_jours;
  const pluie = pluieEfficace(it(meteo.champ(`pluie_${jmin}_${jmax}_${jour.k}`)), cas.ensoleillement, c);
  const tSol = temperatureLocale(it(meteo.champ(`tsol_${jour.k}`)), cas.altitude, c.gradient_sol,
                                 cas.ensoleillement, c.soleil_sol);
  let gel = 0;
  for (let d = jour.k - 6; d <= jour.k; d++) {
    if (temperatureLocale(it(meteo.champ(`tmin_${d}`)), cas.altitude, c.gradient_air) < c.gel_seuil) gel++;
  }
  const f = facteursMeteo(esp, pluie, tSol, gel);
  return { habitat, saison, pluie, tSol, gel, facteurs: f, indice: habitat * saison * f.pluie * f.sol * f.gel };
}
