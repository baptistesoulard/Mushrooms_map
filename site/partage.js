// Partager une page : la feuille de partage du téléphone (messageries, réseaux), sinon le lien
// copié. L'aperçu qu'affichent les messageries vient de l'image de la page (og:image, écrite
// chaque matin par champi/partage.py).
export async function partager({ titre, url }, bouton) {
  if (navigator.share) {
    try {
      await navigator.share({ title: titre, url });
      return;
    } catch (err) {
      if (err.name === "AbortError") return;       // feuille de partage refermée
    }
  }
  const avant = bouton.textContent;
  let copie = false;
  try {
    await navigator.clipboard.writeText(url);
    copie = true;
  } catch {
    copie = copierAncien(url);          // presse-papiers refusé (page sans focus, vieux navigateur)
  }
  bouton.textContent = copie ? "Lien copié" : "Copie impossible : prenez l'adresse de la page";
  setTimeout(() => { bouton.textContent = avant; }, 2500);
}

function copierAncien(texte) {
  const zone = Object.assign(document.createElement("textarea"), { value: texte, readOnly: true });
  zone.style.cssText = "position: fixed; top: 0; opacity: 0;";
  document.body.append(zone);
  zone.select();
  let ok = false;
  try { ok = document.execCommand("copy"); } catch { /* rien à copier */ }
  zone.remove();
  return ok;
}
