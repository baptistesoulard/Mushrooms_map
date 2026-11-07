// Mes alertes : un département, une liste d'espèces, un seuil ; une notification sur cet appareil
// quand l'une de ces espèces devient favorable dans les 7 prochains jours, puis un rappel la veille.
// L'envoi part chaque matin de GitHub Actions (champi/alertes.py). Les choix et l'abonnement de
// l'appareil vont dans alertes.json, dans le dépôt privé du lien de groupe : sans ce lien, pas
// d'alertes (phase de test entre proches, avant les comptes).
import { depuisBase64, versBase64 } from "./coins.js";

const CLE = "champi-alertes";           // déclarée dans a-propos.html : cet appareil et ses alertes
const CLE_SYNCHRO = "champi-synchro";   // le lien de groupe, posé par coins.js
const CLE_NOM = "champi-nom";
const API = "https://api.github.com";
const FICHIER = "alertes.json";
const FORMAT = "champi-alertes";
const SEUILS = { bon: "bonnes conditions", endroits: "bonnes conditions par endroits" };

class ErreurAlertes extends Error {
  constructor(statut) { super(`alertes : ${statut}`); this.statut = statut; }
}

const el = (tag, attrs = {}, ...enfants) => {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") n.className = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) n.setAttribute(k, v === true ? "" : v);
  }
  for (const e of enfants) n.append(e);
  return n;
};

function lire(cle) {
  try { return JSON.parse(localStorage.getItem(cle) || "null"); } catch { return null; }
}
// Le prénom du groupe, gardé tel quel (sans JSON) par coins.js.
function prenom() {
  try { return localStorage.getItem(CLE_NOM) || ""; } catch { return ""; }
}
function ecrire(cle, v) {
  try { if (v == null) localStorage.removeItem(cle); else localStorage.setItem(cle, JSON.stringify(v)); }
  catch { /* gardé le temps de la page */ }
}

// Clé publique en base64url → octets, comme l'attend pushManager.subscribe.
function octets(b64u) {
  const b = atob(b64u.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (b64u.length % 4)) % 4));
  return Uint8Array.from(b, (c) => c.charCodeAt(0));
}

// Le fichier du dépôt après le passage d'un appareil : son entrée remplacée, ou retirée s'il
// n'a plus d'alerte. Les autres appareils n'y sont pour rien.
export function fusionnerAbonne(doc, id, abonne) {
  const autres = (doc?.abonnes || []).filter((a) => a.id !== id);
  return { format: FORMAT, version: 1, abonnes: abonne && abonne.alertes.length ? [...autres, abonne] : autres };
}

// Une alerte par département : en ajouter une pour un département déjà suivi la remplace.
export function ajouterAlerte(alertes, nouvelle) {
  return [...alertes.filter((a) => a.departement !== nouvelle.departement), nouvelle]
    .sort((a, b) => a.departement.localeCompare(b.departement));
}

/** carte : carte.json ; etat() : { departement, espece } affichés. */
export function installerAlertes({ carte, etat }) {
  const $ = (id) => document.getElementById(id);
  const zoneEtat = $("alertes-etat"), liste = $("alertes-liste"), form = $("alertes-form"), arreter = $("alertes-arreter");
  const deps = Object.fromEntries(carte.departements.map((d) => [d.code, d]));
  const noms = Object.fromEntries(carte.especes.map((e) => [e.code, e.nom]));
  const config = carte.alertes || {};
  let moi = lire(CLE) || null;        // { id, alertes: [...] } de cet appareil

  const dire = (texte, ...plus) => zoneEtat.replaceChildren(texte, ...plus);
  const synchro = () => {
    const s = lire(CLE_SYNCHRO);
    return s && typeof s.depot === "string" && typeof s.jeton === "string" ? s : null;
  };
  const installee = matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
  const iphone = /iPhone|iPad/.test(navigator.userAgent);
  const pushPossible = "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;

  // Le formulaire : départements par numéro, espèces de la carte, l'espèce affichée cochée.
  const cle = (code) => code.replace(/^2([AB])$/, "20$1");
  $("alertes-dep").replaceChildren(...carte.departements.filter((d) => d.centre)
    .sort((a, b) => cle(a.code).localeCompare(cle(b.code)))
    .map((d) => el("option", { value: d.code }, `${d.code} – ${d.nom}`)));
  $("alertes-especes").replaceChildren(...carte.especes.map((e) =>
    el("label", { class: "case" }, el("input", { type: "checkbox", name: "espece", value: e.code }), e.nom)));
  const preRemplir = () => {
    $("alertes-dep").value = etat().departement;
    for (const x of $("alertes-especes").querySelectorAll("input")) x.checked = x.value === etat().espece;
  };

  function afficher() {
    liste.replaceChildren(...(moi?.alertes || []).map((a) => el("li", {},
      el("span", {}, `${deps[a.departement]?.nom ?? a.departement} : ${a.especes.map((c) => (noms[c] ?? c).toLowerCase()).join(", ")}`),
      el("span", { class: "cl" }, `${SEUILS[a.seuil]} · `,
        el("button", { type: "button", class: "lien", onclick: () => retirer(a.departement) }, "retirer")))));
    arreter.hidden = !moi?.alertes?.length;
  }

  // Pourquoi les alertes ne sont pas possibles ici, ou rien.
  function obstacle() {
    const s = synchro();
    if (!s) return ["Les alertes passent par le lien de groupe : ouvrez-le d'abord sur cet appareil (",
      el("a", { href: "a-propos.html#alertes" }, "comment faire"), ")."];
    if (s.lecture) return ["Ce lien de groupe est en lecture seule : il ne permet pas d'enregistrer des alertes."];
    if (!pushPossible || (iphone && !installee)) {
      return [iphone ? "Sur iPhone, ajoutez d'abord la carte à l'écran d'accueil (bouton Partager, puis « Sur l'écran d'accueil »), puis ouvrez-la depuis son icône."
        : "Ce navigateur ne reçoit pas de notifications."];
    }
    if (!config.cle_push) return ["Les alertes ne sont pas encore disponibles sur ce site."];
    return null;
  }

  function preparer() {
    // Les alertes sont réservées au groupe (décision du 2026-11-07) : sans lien de groupe sur cet
    // appareil, la section reste cachée, sauf s'il garde des alertes à pouvoir retirer.
    $("alertes").hidden = !synchro() && !moi?.alertes?.length;
    const o = obstacle();
    form.hidden = Boolean(o);
    if (o) { dire(...o); return; }
    preRemplir();
    dire(config.actives ? "" : "Les alertes enregistrées partiront dès que l'envoi sera branché sur le site.");
  }

  async function appel(s, methode, corps) {
    const r = await fetch(`${API}/repos/${s.depot}/contents/${FICHIER}`, {
      method: methode, cache: "no-store",
      headers: { Authorization: `Bearer ${s.jeton}`, Accept: "application/vnd.github+json",
                 ...(corps ? { "Content-Type": "application/json" } : {}) },
      body: corps ? JSON.stringify(corps) : undefined,
    });
    if (!r.ok && ![404, 409, 422].includes(r.status)) throw new ErreurAlertes(r.status);
    return r;
  }

  // Lecture, fusion, écriture, en recommençant si un autre appareil a écrit entre-temps.
  async function enregistrer(id, abonne) {
    const s = synchro();
    for (let essai = 0; essai < 3; essai++) {
      const r = await appel(s, "GET");
      let doc = null, sha;
      if (r.ok) {
        const j = await r.json();
        sha = j.sha;
        try { doc = JSON.parse(depuisBase64(j.content)); } catch { doc = null; }
        if (doc?.format !== FORMAT) throw new ErreurAlertes("fichier");
      }
      const nouveau = fusionnerAbonne(doc, id, abonne);
      const p = await appel(s, "PUT", { message: `Alertes : ${nouveau.abonnes.length} appareil(s)`,
        content: versBase64(JSON.stringify(nouveau, null, 1)), ...(sha ? { sha } : {}) });
      if (p.ok) return;
      if (p.status === 404) throw new ErreurAlertes(404);
    }
    throw new ErreurAlertes("conflit");
  }

  function motif(err) {
    const st = err instanceof ErreurAlertes ? err.statut : null;
    if (st === 401) return "Le jeton du lien de groupe est refusé ou expiré : demandez un nouveau lien.";
    if (st === 403 || st === 404) return "Le lien de groupe ne permet pas d'écrire dans son dépôt.";
    if (st === "fichier") return "Le fichier des alertes du dépôt est illisible : rien n'a été écrasé.";
    return "Pas de réseau, ou GitHub ne répond pas : réessayez dans un moment.";
  }

  async function abonnement() {
    if (Notification.permission !== "granted" && (await Notification.requestPermission()) !== "granted") {
      throw new Error("refus");
    }
    const reg = await navigator.serviceWorker.ready;
    return (await reg.pushManager.getSubscription())
      || reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: octets(config.cle_push) });
  }

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const departement = $("alertes-dep").value;
    const especes = [...$("alertes-especes").querySelectorAll("input:checked")].map((x) => x.value);
    const seuil = form.querySelector('input[name="seuil"]:checked')?.value || "bon";
    if (!especes.length) { dire("Cochez au moins une espèce."); return; }
    dire("Enregistrement…");
    try {
      const sub = await abonnement();
      const id = moi?.id || (crypto.randomUUID ? crypto.randomUUID() : `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`);
      const alertes = ajouterAlerte(moi?.alertes || [], { departement, especes, seuil });
      await enregistrer(id, { id, nom: prenom(), push: sub.toJSON(), alertes, maj: new Date().toISOString() });
      moi = { id, alertes };
      ecrire(CLE, moi);
      afficher();
      const texte = `${deps[departement].nom} : ${especes.map((c) => noms[c].toLowerCase()).join(", ")}, ${SEUILS[seuil]}, sur 7 jours.`;
      dire(`Alerte enregistrée. ${texte}`);
      // Une notification tout de suite : la preuve que cet appareil les affiche.
      (await navigator.serviceWorker.ready).showNotification("Alerte enregistrée", { body: texte, icon: "icone-192.png" })
        .catch(() => {});
    } catch (err) {
      console.error(err);
      dire(err.message === "refus"
        ? "Notifications refusées : autorisez-les pour ce site dans les réglages du navigateur ou du téléphone."
        : motif(err));
    }
  });

  // Garder les alertes données ; sans alerte, l'appareil sort du fichier et se désabonne.
  async function garder(alertes) {
    if (!moi) return;
    try {
      const sub = await (await navigator.serviceWorker.ready).pushManager.getSubscription();
      await enregistrer(moi.id, alertes.length && sub
        ? { id: moi.id, nom: prenom(), push: sub.toJSON(), alertes, maj: new Date().toISOString() } : null);
      if (!alertes.length) await sub?.unsubscribe();
      moi = alertes.length ? { ...moi, alertes } : null;
      ecrire(CLE, moi);
      afficher();
      dire(alertes.length ? "Alerte retirée." : "Plus aucune alerte sur cet appareil.");
    } catch (err) {
      console.error(err);
      dire(motif(err));
    }
  }
  const retirer = (departement) => garder(moi.alertes.filter((a) => a.departement !== departement));
  arreter.addEventListener("click", () => garder([]));

  afficher();
  preparer();
  window.addEventListener("hashchange", preparer);        // un lien de groupe tout juste ouvert
  return { rafraichir: preRemplir };
}
