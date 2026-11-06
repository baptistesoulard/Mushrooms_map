// Le site passe sur son propre domaine (décision du 2026-11-06), toujours chez GitHub Pages.
// Le navigateur range les coins, le lien de groupe et les alertes par adresse de site : ils ne
// suivront pas seuls. Sur l'ancienne adresse (*.github.io), un bandeau le dit avant la bascule.
// Une fois le domaine déclaré dans les réglages Pages, l'ancienne adresse renvoie vers la
// nouvelle et ce bandeau ne paraît plus nulle part : il pourra être retiré.
export const NOUVELLE_ADRESSE = "https://champimeteo.fr/";

function nombreCoins() {
  try {
    const v = JSON.parse(localStorage.getItem("champi-coins") || "[]");
    return Array.isArray(v) ? v.length : 0;
  } catch { return 0; }
}

function aUnGroupe() {
  try { return Boolean(localStorage.getItem("champi-synchro")); } catch { return false; }
}

function aDesAlertes() {
  try { return Boolean(JSON.parse(localStorage.getItem("champi-alertes") || "null")?.alertes?.length); }
  catch { return false; }
}

export function installerDemenagement() {
  if (!location.hostname.endsWith(".github.io")) return;
  const zone = document.querySelector(".panneau, .page");
  if (!zone) return;
  const nom = NOUVELLE_ADRESSE.replace(/^https:\/\/|\/$/g, "");
  const p = document.createElement("p");
  p.className = "alerte demenagement";
  const lien = document.createElement("a");
  lien.href = NOUVELLE_ADRESSE;
  lien.textContent = nom;
  p.append("Le site déménage sur ", lien, ". ");
  const n = nombreCoins();
  if (n) {
    p.append(`Vos ${n} coin${n > 1 ? "s" : ""} ne suivront pas seuls : sauvegardez-les, puis importez le `
      + "fichier là-bas (Mes outils). ");
    const sauver = document.getElementById("coins-sauver");
    if (sauver) {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = "Sauvegarder mes coins";
      b.addEventListener("click", () => sauver.click());
      p.append(b, " ");
    } else {
      const carte = document.createElement("a");
      carte.href = new URL("carte/", import.meta.url).href;   // ce module est à la racine du site
      carte.textContent = "Ouvrir la carte pour les sauvegarder";
      p.append(carte, ". ");
    }
  }
  if (aUnGroupe()) p.append("Pour le groupe, rouvrez votre lien de groupe sur la nouvelle adresse. ");
  // Un abonnement aux alertes reste lié à l'ancienne adresse : il continue de sonner (le lien de la
  // notification mène au nouveau site), mais ne se modifie plus. Un réabonnement là-bas sans
  // retrait ici ferait sonner l'appareil deux fois.
  if (aDesAlertes()) p.append("Vos alertes continuent d'arriver ; pour les changer, retirez-les d'abord ici "
    + "(Mes outils), puis abonnez-vous là-bas.");
  zone.prepend(p);
}
