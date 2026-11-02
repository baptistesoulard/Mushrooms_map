// La présentation de la première visite : cinq écrans courts, une seule fois par navigateur (clé
// champi-guide, déclarée dans a-propos.html), puis à la demande (« Revoir la présentation »).
const CLE = "champi-guide";

const ETAPES = (etroit) => [
  ["Où chercher, jour par jour",
    "Choisissez une espèce et un jour : la carte colore les forêts selon un indice de conditions " +
    "favorables, du plus clair (faible) au plus foncé (excellent). Il tient compte de la forêt, du sol, " +
    "de la pluie des dernières semaines et de la météo des sept prochains jours."],
  ["Rapprochez-vous, touchez une forêt",
    "De près, chaque case de 50 m a sa fiche : son indice sur 100, ce qui le limite, la pluie, le sol, " +
    "le gel, et si la forêt est publique ou privée. « Y aller » ouvre l'itinéraire."],
  [etroit ? "Tirez le panneau vers le haut" : "Le panneau, à gauche",
    "En haut, l'espèce (un toucher ouvre la liste illustrée) et le jour. Puis quatre onglets : « Ici » " +
    "classe les espèces pour la zone affichée ; « Département » donne le verdict, la semaine et les " +
    "communes ; « L'espèce », sa fiche ; « Mes outils », vos coins et vos alertes."],
  ["Vos coins, vos alertes",
    `${etroit ? "Un appui long" : "Un clic droit"} sur la carte note une trouvaille, gardée dans ce navigateur. ` +
    "« Mes alertes » prévient quand une espèce devient favorable dans votre département."],
  ["Avant de cueillir",
    "La carte dit où chercher, jamais quoi manger : faites contrôler toute récolte par un pharmacien ou " +
    "une société mycologique. En forêt privée, les champignons appartiennent au propriétaire."],
];

function dejaVu() {
  try { return localStorage.getItem(CLE) === "vu"; } catch { return true; }   // stockage bloqué : ne pas insister
}

export function installerGuide(dialogue, { etroit }) {
  let k = 0, etapes = [];
  const $ = (id) => dialogue.querySelector(`#${id}`);

  function montrer() {
    const [titre, texte] = etapes[k];
    $("guide-etape").textContent = `${k + 1} sur ${etapes.length}`;
    $("guide-titre").textContent = titre;
    $("guide-texte").textContent = texte;
    dialogue.querySelector(".legende-guide").hidden = k > 0;        // l'échelle des couleurs, au premier écran
    $("guide-passer").hidden = k === etapes.length - 1;
    $("guide-suivant").textContent = k === etapes.length - 1 ? "C'est parti" : "Suivant";
  }

  function ouvrir() {
    etapes = ETAPES(etroit());
    k = 0;
    montrer();
    if (!dialogue.open) dialogue.showModal();
    $("guide-suivant").focus();
  }

  $("guide-suivant").addEventListener("click", () => {
    if (++k < etapes.length) montrer();
    else dialogue.close();
  });
  $("guide-passer").addEventListener("click", () => dialogue.close());
  dialogue.addEventListener("close", () => {
    try { localStorage.setItem(CLE, "vu"); } catch { /* navigation privée : elle reviendra */ }
  });
  return { ouvrir, premiereVisite: () => !dejaVu() };
}
