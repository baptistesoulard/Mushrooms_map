// Pages Méthode et Face aux observations : tableaux construits depuis les JSON publiés,
// pour qu'un seuil changé dans champi/especes.py ne laisse jamais une page en retard.

const fr = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 });
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
      ["Altitude", `pleine jusqu'à ${fr.format(a1)} m, nulle au-dessus de ${fr.format(a2)} m (à ${fr.format(regles.communs.latitude_ref)}° N), pas de plancher`],
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
  for (const e of Object.values(v.especes)) {
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
    } else {
      ligne("Habitat", h.n, "—", `trop peu de cas (moins de ${v.min_cas})`);
    }
    if (m.auc_mois !== undefined) {
      ligne("Météo, à mois égal", m.n, auc(m.auc_mois, m.ic_mois), lecture(m.auc_mois, m.ic_mois));
      ligne("Météo, sur la saison", m.n, auc(m.auc_saison, m.ic_saison), lecture(m.auc_saison, m.ic_saison));
      ligne("Calendrier seul (référence)", m.n, auc(m.auc_calendrier, m.ic_calendrier),
        `indice : ${ecart(m.ic_ecart, "mieux que le calendrier", "moins bien que le calendrier")}`);
    } else {
      ligne("Météo", m.n, "—", `trop peu de cas datés en saison (moins de ${v.min_cas})`);
    }
    s.append(el("div", { class: "tableau" }, t));
    s.append(el("p", { class: "muet" }, `${e.observations} observations datées au jour dans le département.` +
      (h.part_hors_foret !== undefined ? ` ${pct(h.part_hors_foret)} des cas d'habitat tombent hors forêt selon la BD Forêt.` : "")));
    zone.append(s);
  }
}

if (document.getElementById("especes")) methode();
if (document.getElementById("resultats")) validation();
