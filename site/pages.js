// Pages Méthode et Face aux observations : tableaux construits depuis les JSON publiés,
// pour qu'un seuil changé dans champi/especes.py ne laisse jamais une page en retard.
// Chargé aussi par les pages générées chaque matin (champi/pages.py), qui se lisent sans lui.
import { installerDemenagement } from "./demenagement.js";
import { partager } from "./partage.js";

const fr = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 });
const fr2 = new Intl.NumberFormat("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });   // seuils de l'indice
const pct = (v) => `${Math.round(v * 100)} %`;
const MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
  "septembre", "octobre", "novembre", "décembre"];
const ROCHES = { 1: "calcaire", 2: "siliceuse", 3: "mixte ou argileuse" };

const el = (tag, attrs = {}, ...enfants) => {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  for (const e of enfants) n.append(e);
  return n;
};

function dateCourte(mmjj) {
  const [m, j] = mmjj.split("-").map(Number);
  return `${j === 1 ? "1er" : j} ${MOIS[m - 1]}`;
}

function tableau(lignes) {
  const t = el("table");
  for (const [k, v] of lignes) t.append(el("tr", {}, el("th", { scope: "row" }, k), el("td", {}, v)));
  return el("div", { class: "tableau" }, t);
}

async function methode() {
  const [regles, carte] = await Promise.all([
    fetch("data/especes.json").then((r) => r.json()),
    fetch("data/carte.json").then((r) => r.json()),
  ]);
  const essences = carte.legendes.essences;
  const zone = document.getElementById("especes");
  zone.replaceChildren();
  for (const e of regles.especes) {
    const par = (min, max) => Object.entries(e.essences)
      .filter(([k, v]) => Number(k) > 0 && v >= min && v < max)
      .sort((a, b) => b[1] - a[1]).map(([k]) => essences[k].toLowerCase()).join(", ") || "—";
    const [s0, s1, s2, s3] = e.saison;
    const [a1, a2] = e.altitude;
    const [t0, t1, t2, t3] = e.sol;
    const [jmin, jmax] = e.pluie_jours;
    const [p0, p1] = e.pluie_mm;
    const roches = Object.entries(ROCHES).map(([k, n]) => `${n} ${fr.format(e.roches[k])}`).join(" · ");
    const lignes = [
      ["Saison", `pleine du ${dateCourte(s1)} au ${dateCourte(s2)}, possible du ${dateCourte(s0)} au ${dateCourte(s3)} (à ${fr.format(regles.communs.latitude_ref)}° N)`],
      ["Aspect", e.description],
      ["Milieu", e.habitat_texte],
      ["Forêts favorables", par(0.8, 2)],
      ["Forêts possibles", par(0.4, 0.8)],
      ["Roche (affinité)", roches],
      ...(e.sol_ph ? [["pH du sol", `plein de ${fr.format(e.ph[1])} à ${fr.format(e.ph[2])}, au plus bas ` +
        `${fr.format(e.ph_plancher)} sous ${fr.format(e.ph[0])} et au-dessus de ${fr.format(e.ph[3])} ; ` +
        "remplace la roche là où SoilGrids le connaît"]] : []),
      ["Altitude", `pleine jusqu'à ${fr.format(a1)} m, nulle au-dessus de ${fr.format(a2)} m (à ${fr.format(regles.communs.latitude_ref)}° N), ` +
        (e.plancher[1] > 0 ? `nulle sous ${fr.format(e.plancher[0])} m, pleine dès ${fr.format(e.plancher[1])} m (espèce de montagne)` : "pas de plancher")],
      ["Pluie", `cumul entre ${jmax} et ${jmin} jours avant : pleine pousse au-delà de ${fr.format(p1)} mm, rien sous ${fr.format(p0)} mm`],
      ["Sol", `moyenne des 7 jours précédents : optimum de ${fr.format(t1)} à ${fr.format(t2)} °C, rien sous ${fr.format(t0)} °C ni au-dessus de ${fr.format(t3)} °C`],
      ["Gel", `chaque jour de gel de la semaine multiplie l'indice par ${fr.format(e.gel)}`],
      ["En pratique", e.meteo_texte],
    ];
    if (e.confusions) lignes.push(["Confusions possibles", e.confusions]);
    const carteEsp = el("section", { class: "carte-espece" },
      el("h3", {}, `${e.nom} `, el("span", { class: "latin" }, e.latin)), tableau(lignes));
    for (const l of e.limites) carteEsp.append(el("p", { class: "muet" }, `Limite : ${l}`));
    zone.append(carteEsp);
  }
  const c = regles.communs;
  document.getElementById("communs").replaceChildren(tableau([
    ["Température de l'air", `−${fr.format(c.gradient_air * 100)} °C par 100 m d'altitude`],
    ["Température du sol", `−${fr.format(c.gradient_sol * 100)} °C par 100 m ; jusqu'à +${fr.format(c.soleil_sol)} °C sur un versant sud très raide, autant en moins au nord`],
    ["Versant au soleil", `jusqu'à ${pct(c.secheresse_sud)} de la pluie « perdue » par évaporation sur un versant sud très raide`],
    ["Jour de gel", `température minimale de l'air sous ${fr.format(c.gel_seuil)} °C`],
    ["Forêt ouverte", `indice multiplié par ${fr.format(c.foret_ouverte)}`],
    ["Pente", `pleine jusqu'à ${fr.format(c.pente[0])}°, réduite jusqu'à ${pct(c.pente[2])} à ${fr.format(c.pente[1])}° et au-delà`],
    ["Latitude (loi de Hopkins)", `règles écrites à ${fr.format(c.latitude_ref)}° N ; par degré vers le sud, saison de printemps ${fr.format(c.hopkins_jours)} jours plus tôt, d'automne ${fr.format(c.hopkins_jours)} jours plus tard, plafond d'altitude ${fr.format(c.hopkins_metres)} m plus haut`],
    ["Classes de l'indice", carte.classes.slice(1).map((k, i) => `${k.nom.toLowerCase()} dès ${fr2.format(carte.classes[i].seuil)}`).join(" · ") +
      ` ; sous ${fr2.format(carte.classes[0].seuil)}, ${carte.classes[0].nom.toLowerCase()} (sans couleur). Seuils fixes : un jour sans pousse donne une carte pâle`],
    ["Verdict d'un département", `bonnes conditions quand ${pct(carte.niveaux.bon)} de ses forêts au moins ont un indice bon ou mieux, par endroits dès ${pct(carte.niveaux.endroits)}`],
    ...(carte.habituel ? [["Ce qui est habituel", `part des jours de la même décade où la météo de l'espèce (saison × pluie × sol × gel) atteint ${fr2.format(carte.habituel.seuil)}, de ${carte.habituel.periode[0]} à ${carte.habituel.periode[1]} (réanalyse ERA5), aux lieux d'observation de la vérification`]] : []),
  ]));
  document.getElementById("references").replaceChildren(...regles.references.map((r) => el("li", {}, r)));
}

function lecture(auc, ic) {
  if (ic[0] > 0.5) return "mieux que le hasard";
  if (ic[1] < 0.5) return "moins bien que le hasard";
  return "pas de différence nette avec le hasard";
}

function ecart(ic, mieux, pire) {
  if (ic[0] > 0) return mieux;
  if (ic[1] < 0) return pire;
  return "pas de différence nette";
}

const auc = (v, ic) => `${pct(v)} [${pct(ic[0])} – ${pct(ic[1])}]`;

async function validation() {
  const zone = document.getElementById("resultats");
  let v;
  try {
    v = await fetch("data/validation.json").then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); });
  } catch {
    zone.replaceChildren(el("p", {}, "Les résultats ne sont pas encore publiés."));
    return;
  }
  zone.replaceChildren(el("p", { class: "muet" },
    `Calculé le ${new Date(v.calcule_le).toLocaleDateString("fr-FR", { dateStyle: "long" })}, ` +
    `observations de ${v.periode[0]} à ${v.periode[1]}. Habitat : positions connues à ` +
    `${fr.format(v.incertitude_habitat_m / 1000)} km près ; météo : à ${fr.format(v.incertitude_meteo_m / 1000)} km près.`));
  for (const [code, r] of Object.entries(v.regions)) {
    const fond = el("p", { class: "muet" }, `Fond de comparaison : ${r.fond.toLocaleString("fr-FR")} sorties ` +
      "où d'autres champignons ont été observés dans cette zone.");
    const sections = Object.values(r.especes).map((e) => espece(e, v.min_cas, code === "france" ? "en France" : "dans cette zone"));
    if (code === "france") {
      zone.append(el("h2", {}, r.nom), fond, ...sections);
    } else {
      const testees = Object.values(r.especes).filter((e) => e.habitat.auc !== undefined || e.meteo.auc_mois !== undefined).length;
      zone.append(el("details", { class: "region" },
        el("summary", {}, el("strong", {}, r.nom), testees
          ? ` — ${testees} espèce${testees > 1 ? "s" : ""} sur ${Object.keys(r.especes).length} avec assez de cas`
          : " — trop peu d'observations pour conclure"),
        fond, ...sections));
    }
  }
}

// Les tests d'une espèce dans une zone.
function espece(e, minCas, ou) {
  const s = el("section", { class: "carte-espece" }, el("h3", {}, e.nom));
  const h = e.habitat;
  const m = e.meteo;
  const t = el("table", {}, el("tr", {}, el("th", {}, "Test"), el("th", { class: "num" }, "Cas"),
    el("th", {}, "Résultat"), el("th", {}, "Lecture")));
  const ligne = (test, n, res, lec) => t.append(el("tr", {}, el("td", {}, test),
    el("td", { class: "num" }, String(n)), el("td", {}, res), el("td", {}, lec)));
  if (h.auc !== undefined) {
    ligne("Habitat", h.n, auc(h.auc, h.ic), lecture(h.auc, h.ic));
    ligne("Forêt seule (référence)", h.n, auc(h.auc_foret, h.ic_foret),
      `habitat : ${ecart(h.ic_ecart, "mieux que la forêt seule", "moins bien que la forêt seule")}`);
    if (h.auc_ph !== undefined) {
      ligne("Habitat, pH du sol au lieu de la roche", h.n, `${pct(h.auc_ph)} (roche : ${pct(h.auc_roche)})`,
        `pH : ${ecart(h.ic_ecart_ph, "mieux que la roche", "moins bien que la roche")}`);
    }
  } else if (h.sans_carte) {
    ligne("Habitat", h.n, "—", "pas vérifié : une espèce des prés, sans carte fine");
  } else {
    ligne("Habitat", h.n, "—", `trop peu de cas (moins de ${minCas})`);
  }
  if (m.auc_mois !== undefined) {
    ligne("Météo, à mois égal", m.n, auc(m.auc_mois, m.ic_mois), lecture(m.auc_mois, m.ic_mois));
    ligne("Météo, sur la saison", m.n, auc(m.auc_saison, m.ic_saison), lecture(m.auc_saison, m.ic_saison));
    ligne("Calendrier seul (référence)", m.n, auc(m.auc_calendrier, m.ic_calendrier),
      `indice : ${ecart(m.ic_ecart, "mieux que le calendrier", "moins bien que le calendrier")}`);
  } else {
    ligne("Météo", m.n, "—", `trop peu de cas datés en saison (moins de ${minCas})`);
  }
  s.append(el("div", { class: "tableau" }, t));
  s.append(el("p", { class: "muet" }, `${e.observations.toLocaleString("fr-FR")} observations datées au jour ${ou}.` +
    (h.part_hors_foret !== undefined ? ` ${pct(h.part_hors_foret)} des cas d'habitat tombent hors forêt selon la BD Forêt.` : "")));
  return s;
}

// Accueil : « Mon département » mène au dernier département affiché sur la carte (gardé tel quel
// par carte.js), sinon à la liste des départements.
function monDepartement(bouton) {
  let code = null;
  try { code = localStorage.getItem("champi-departement"); } catch { /* rien de gardé */ }
  const lien = code && document.querySelector(`[data-departement="${CSS.escape(code)}"]`);
  if (!lien) return;
  bouton.href = lien.getAttribute("href");
  bouton.textContent = `Mon département : ${lien.textContent.replace(/^\S+\s/, "")}`;
  const choix = document.getElementById("aller-departement");
  if (choix) choix.value = code;
}

// Accueil : le choix d'un département mène à sa page ; sans choix, à la liste.
function allerDepartement(formulaire) {
  const choix = formulaire.querySelector("select");
  const aller = () => { location.href = choix.value ? `departements/${choix.value}.html` : "departements/"; };
  choix.addEventListener("change", aller);
  formulaire.addEventListener("submit", (ev) => { ev.preventDefault(); aller(); });
}

if (document.getElementById("especes")) methode();
if (document.getElementById("resultats")) validation();
// Les espèces : filtrer les fiches (toutes, en saison, forêt, prés).
function filtres(barre) {
  barre.hidden = false;
  const fiches = [...document.querySelectorAll(".fiches-especes li")];
  for (const b of barre.querySelectorAll("button")) {
    b.addEventListener("click", () => {
      const f = b.dataset.filtre;
      for (const x of barre.querySelectorAll("button")) x.setAttribute("aria-pressed", String(x === b));
      for (const li of fiches) {
        li.hidden = !(f === "tout" || (f === "saison" ? li.dataset.saison === "oui" : li.dataset.milieu === f));
      }
    });
  }
}

// Les départements : la carte se repeint à l'espèce et au jour choisis, le classement aussi.
const NIVEAUX = ["hors saison", "conditions défavorables", "pousse possible, sans plus",
  "bonnes conditions par endroits", "bonnes conditions"];
function carteDepartements(choix) {
  const d = JSON.parse(document.getElementById("niveaux-deps").textContent);
  const liens = [...document.querySelectorAll(".carte-deps a[data-dep]")];
  let espece = d.defaut, jour = 0;
  // L'espèce regardée sur la carte, si elle en a une (clé déclarée dans a-propos.html).
  try {
    const vue = localStorage.getItem("champi-espece");
    if (vue && d.especes[vue]) espece = vue;
  } catch { /* rien de gardé */ }
  choix.hidden = false;
  const lien = (c) => el("a", { href: `${c}.html` }, d.noms[c] ?? c);
  function peindre() {
    const x = d.especes[espece];
    const niveaux = x.niveaux[jour];
    liens.forEach((a, i) => {
      const n = niveaux[i];
      a.querySelector("path").setAttribute("class", `n${n}`);
      a.querySelector("title").textContent = `${d.noms[a.dataset.dep]} : ${n === "x" ? "rien de calculé" : NIVEAUX[n]}`;
    });
    document.getElementById("titre-carte-deps").textContent = `${x.nom}, ${d.jours[jour]}`;
    const [bons, endroits] = x.tete[jour];
    const zone = document.getElementById("classement-deps");
    zone.replaceChildren();
    for (const [codes, quoi] of [[bons, "Bonnes conditions"], [endroits, "Par endroits"]]) {
      if (!codes.length) continue;
      const p = el("p", {}, el("strong", {}, quoi), ` (${codes.length}) : `);
      codes.forEach((c, k) => p.append(k ? ", " : "", lien(c)));
      p.append(".");
      zone.append(p);
    }
    if (!bons.length && !endroits.length) zone.append(el("p", {}, "Aucun département aux bonnes conditions ce jour-là."));
    for (const b of choix.querySelectorAll("[data-espece]")) b.setAttribute("aria-pressed", String(b.dataset.espece === espece));
    for (const b of choix.querySelectorAll("[data-jour]")) b.setAttribute("aria-pressed", String(Number(b.dataset.jour) === jour));
  }
  for (const b of choix.querySelectorAll("[data-espece]")) b.addEventListener("click", () => { espece = b.dataset.espece; peindre(); });
  for (const b of choix.querySelectorAll("[data-jour]")) b.addEventListener("click", () => { jour = Number(b.dataset.jour); peindre(); });
  if (espece !== d.defaut) peindre();
}

// Une page calculée pour un jour passé : la mise à jour de la nuit n'a pas eu lieu (GitHub lance
// parfois son départ programmé avec des heures de retard). Le dire en tête, comme la carte.
function perime(p) {
  const jour = p.dataset.premierJour;
  if (jour >= new Date().toLocaleDateString("sv-SE", { timeZone: "Europe/Paris" })) return;
  const [a, m, j] = jour.split("-").map(Number);
  const nom = new Date(Date.UTC(a, m - 1, j)).toLocaleDateString("fr-FR", { weekday: "long", timeZone: "UTC" });
  document.querySelector(".page").prepend(el("p", { class: "alerte perime" },
    `Cette page date du ${nom} ${j === 1 ? "1er" : j} ${MOIS[m - 1]} : la mise à jour de cette nuit n'a pas `
    + "encore eu lieu, et « aujourd'hui » y désigne ce jour-là."));
}

installerDemenagement();
const datee = document.querySelector("[data-premier-jour]");
if (datee) perime(datee);
if (document.getElementById("mon-departement")) monDepartement(document.getElementById("mon-departement"));
for (const b of document.querySelectorAll("[data-filtres]")) filtres(b);
for (const c of document.querySelectorAll("[data-carte-deps]")) carteDepartements(c);
for (const f of document.querySelectorAll("[data-aller-departement]")) allerDepartement(f);
// Le bouton Partager des pages générées : caché tant que ce script n'a pas tourné.
for (const b of document.querySelectorAll("[data-partager]")) {
  b.hidden = false;
  b.addEventListener("click", () => partager({ titre: document.title, url: location.href.split("#")[0] }, b));
}
