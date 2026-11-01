// Sur téléphone, le panneau de la carte est une feuille qui glisse du bas, par-dessus la carte
// plein écran : trois hauteurs (repliée sur ses premières lignes, la moitié de l'écran, presque
// tout), qu'on tire par la poignée ou qu'on change d'un appui (ou au clavier). Sur un écran
// large, rien de tout cela : le panneau reste à gauche de la carte (style.css, même largeur).
const ETROIT = "(max-width: 820px)";
const MARGE_HAUT = 56;               // px de carte gardés au-dessus de la feuille dépliée
const ORDRE = ["bas", "milieu", "haut"];

// bas() : la hauteur repliée, en px (ce qu'elle doit laisser voir dépend de son contenu).
export function installerFeuille(panneau, poignee, { bas }) {
  const etroit = matchMedia(ETROIT);
  const hauteurs = {
    bas: () => Math.min(bas(), innerHeight / 2),
    milieu: () => Math.round(innerHeight * 0.52),
    haut: () => innerHeight - MARGE_HAUT,
  };
  let etat = "bas";

  function poser(nouveau) {
    etat = nouveau;
    panneau.dataset.etat = etat;
    if (!etroit.matches) { panneau.style.removeProperty("height"); return; }
    panneau.style.height = `${hauteurs[etat]()}px`;
    poignee.setAttribute("aria-expanded", String(etat !== "bas"));
    poignee.querySelector(".lecteur").textContent = etat === "haut" ? "Réduire le panneau" : "Agrandir le panneau";
    if (etat === "bas") panneau.scrollTop = 0;
  }

  // La feuille suit le doigt, puis se pose à la hauteur la plus proche, ou à la suivante dans le
  // sens d'un geste rapide. Un appui sans glisser (ou Entrée) passe à la hauteur suivante.
  let depart = null, sauterClic = false;
  poignee.addEventListener("pointerdown", (ev) => {
    if (!etroit.matches) return;
    depart = { y: ev.clientY, h: panneau.getBoundingClientRect().height, t: performance.now(), bouge: false };
    poignee.setPointerCapture(ev.pointerId);
    panneau.classList.add("glisse");
  });
  poignee.addEventListener("pointermove", (ev) => {
    if (!depart) return;
    const dy = depart.y - ev.clientY;
    if (Math.abs(dy) > 6) depart.bouge = true;
    panneau.style.height = `${Math.min(Math.max(depart.h + dy, hauteurs.bas()), hauteurs.haut())}px`;
  });
  const lacher = (ev) => {
    if (!depart) return;
    const d = depart;
    depart = null;
    panneau.classList.remove("glisse");
    if (!d.bouge) return;                       // un simple appui : le clic s'en charge
    sauterClic = true;
    const h = panneau.getBoundingClientRect().height;
    const vitesse = (d.y - ev.clientY) / Math.max(performance.now() - d.t, 1);     // px/ms, > 0 vers le haut
    let cible = ORDRE.reduce((m, e) => (Math.abs(hauteurs[e]() - h) < Math.abs(hauteurs[m]() - h) ? e : m));
    if (Math.abs(vitesse) > 0.5) {
      const i = ORDRE.indexOf(etat) + Math.sign(vitesse);
      cible = ORDRE[Math.min(Math.max(i, 0), ORDRE.length - 1)];
    }
    poser(cible);
  };
  poignee.addEventListener("pointerup", lacher);
  poignee.addEventListener("pointercancel", lacher);
  poignee.addEventListener("click", () => {
    if (sauterClic) { sauterClic = false; return; }
    poser(ORDRE[(ORDRE.indexOf(etat) + 1) % ORDRE.length]);
  });
  addEventListener("resize", () => poser(etat));
  etroit.addEventListener("change", () => poser(etat));
  poser("bas");

  return { poser, etat: () => etat, etroit: () => etroit.matches, hauteur: (e) => hauteurs[e]() };
}
