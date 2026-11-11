// La présentation de la carte. À la première visite, un seul écran (décision du 2026-11-11 : cinq
// écrans avant la carte, c'était trop) : l'échelle des couleurs, comment s'en servir, l'avertissement,
// et « Voir la carte ». La visite guidée (les écrans suivants) reste à un toucher, depuis cet écran
// ou « Revoir la présentation ». Vue une fois par navigateur (clé champi-guide, déclarée dans
// a-propos.html).
const CLE = "champi-guide";

const ETAPES = (etroit) => [
  ["Où chercher, jour par jour",
    "Choisissez une espèce et un jour : la carte colore les forêts, du plus clair (conditions faibles) au " +
    "plus foncé (excellentes). Zoomez, puis touchez une forêt pour voir sa fiche."],
  ["Rapprochez-vous, touchez une forêt",
    "De près, chaque zone de 250 m a sa fiche : son indice sur 100, ce qui le limite, la pluie, le sol, " +
    "le gel, et si ses forêts sont surtout publiques ou privées (en forêt privée, les champignons sont au " +
    "propriétaire). « Y aller » ouvre l'itinéraire."],
  [etroit ? "Tirez le panneau vers le haut" : "Le panneau, à gauche",
    "En haut, l'espèce (un toucher ouvre la liste illustrée) et le jour. Puis quatre onglets : « Ici » " +
    "classe les espèces pour la zone affichée ; « Département » donne le verdict, la semaine et les " +
    "communes ; « L'espèce », sa fiche ; « Mes outils », vos coins et l'exploration des forêts."],
  ["Vos coins",
    `${etroit ? "Un appui long" : "Un clic droit"} sur la carte note une trouvaille, gardée dans ce navigateur. ` +
    "Vous pouvez les sauvegarder, les envoyer à un proche, ou les partager avec un groupe par un lien privé."],
];

function dejaVu() {
  try { return localStorage.getItem(CLE) === "vu"; } catch { return true; }   // stockage bloqué : ne pas insister
}

export function installerGuide(dialogue, { etroit }) {
  let k = 0, etapes = [], accueil = true;    // accueil : l'écran unique de la première visite
  const $ = (id) => dialogue.querySelector(`#${id}`);

  function montrer() {
    const [titre, texte] = etapes[k];
    const derniere = k === etapes.length - 1;
    $("guide-etape").hidden = accueil;
    $("guide-etape").textContent = `${k + 1} sur ${etapes.length}`;
    $("guide-titre").textContent = titre;
    $("guide-texte").textContent = texte;
    // L'échelle des couleurs et l'avertissement, au premier écran.
    dialogue.querySelector(".legende-guide").hidden = k > 0;
    $("guide-avertissement").hidden = k > 0;
    $("guide-passer").textContent = accueil ? "Visite guidée" : "Passer";
    $("guide-passer").hidden = !accueil && derniere;
    $("guide-suivant").textContent = accueil ? "Voir la carte" : derniere ? "C'est parti" : "Suivant";
  }

  // `visite` : la présentation complète, écran par écran (« Revoir la présentation ») ; sinon
  // l'écran d'accueil seul.
  function ouvrir({ visite = false } = {}) {
    etapes = ETAPES(etroit());
    k = 0;
    accueil = !visite;
    montrer();
    if (!dialogue.open) dialogue.showModal();
    $("guide-suivant").focus();
  }

  $("guide-suivant").addEventListener("click", () => {
    if (!accueil && ++k < etapes.length) montrer();
    else dialogue.close();
  });
  $("guide-passer").addEventListener("click", () => {
    if (!accueil) { dialogue.close(); return; }
    accueil = false;                  // la visite guidée, à partir du deuxième écran
    k = 1;
    montrer();
    $("guide-suivant").focus();
  });
  dialogue.addEventListener("close", () => {
    try { localStorage.setItem(CLE, "vu"); } catch { /* navigation privée : elle reviendra */ }
  });
  return { ouvrir, premiereVisite: () => !dejaVu() };
}
