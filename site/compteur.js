// Le compteur de visites (2026-11-24) : GoatCounter, sans cookie ni donnée personnelle (déclaré dans
// a-propos.html). Pas le script de GoatCounter : son rôle tient ici en quelques lignes, l'adresse
// de la page vue envoyée à soulabat.goatcounter.com, rien d'autre. Ne compte que sur le site en
// ligne (pas sur le poste), ni les robots du navigateur (webdriver), ni les aperçus préchargés.
const COMPTEUR = "https://soulabat.goatcounter.com/count";
const SITE = /(^|\.)champimeteo\.fr$/;

function envoyer(params) {
  if (!SITE.test(location.hostname) || navigator.webdriver) return;
  const q = new URLSearchParams({ ...params, rnd: Math.random().toString(36).slice(2) });
  try { new Image().src = `${COMPTEUR}?${q}`; } catch { /* sans compteur, la page marche */ }
}

// Un événement de la carte (« espece-cepe », « carte-fine-ouverte ») : compté à part des pages.
export function evenement(nom) {
  envoyer({ p: nom, t: nom, e: "true" });
}

function pageVue() {
  const r = document.referrer && !document.referrer.startsWith(location.origin) ? document.referrer : "";
  envoyer({ p: location.pathname, t: document.title, r, s: String(screen.width) });
}

// Une page préchargée (onglet en arrière-plan) n'est comptée qu'une fois vue.
if (document.visibilityState === "prerender" || document.prerendering) {
  document.addEventListener("prerenderingchange", pageVue, { once: true });
} else {
  pageVue();
}
