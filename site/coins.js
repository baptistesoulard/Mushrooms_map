// Mes coins : les trouvailles de l'utilisateur, gardées dans CE navigateur et nulle part
// ailleurs (le site n'a pas de serveur). Elles se partagent par fichier, avec qui l'on veut :
// le partage n'envoie que ses propres coins, jamais ceux qu'un ami a confiés.
const CLE = "champi-coins";            // déclarée dans a-propos.html
const RAYON_M = 100;                   // deux trouvailles à moins de 100 m : le même coin
const ZOOM_PRECIS = 14;                // en deçà, un appui long tomberait à des centaines de mètres
const FORMAT = "champi-coins";

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

const auJour = () => new Date().toLocaleDateString("sv-SE", { timeZone: "Europe/Paris" });
const majuscule = (t) => t.charAt(0).toUpperCase() + t.slice(1);
const dateFr = (iso) => new Date(`${iso}T12:00:00`).toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" });

function distance(a, b) {
  const dy = (a.lat - b.lat) * 111320;
  const dx = (a.lon - b.lon) * 111320 * Math.cos(a.lat * Math.PI / 180);
  return Math.hypot(dx, dy);
}

function nouvelId() {
  return crypto.randomUUID ? crypto.randomUUID() : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

// Un coin venu d'un fichier n'est gardé que s'il a la forme attendue.
function valide(c, codes) {
  return c && typeof c.id === "string" && Number.isFinite(c.lat) && Number.isFinite(c.lon)
    && Math.abs(c.lat) <= 90 && Math.abs(c.lon) <= 180 && codes.has(c.espece)
    && /^\d{4}-\d{2}-\d{2}$/.test(c.date) && (c.de == null || typeof c.de === "string");
}

function propre(c) {
  const o = { id: c.id, lat: Math.round(c.lat * 1e5) / 1e5, lon: Math.round(c.lon * 1e5) / 1e5,
              espece: c.espece, date: c.date };
  if (c.note) o.note = String(c.note).slice(0, 200);
  if (c.de) o.de = String(c.de).slice(0, 40);
  return o;
}

// Les trouvailles d'une espèce regroupées en coins : chacune rejoint le coin de la plus récente
// à moins de RAYON_M.
export function regrouper(trouvailles) {
  const groupes = [];
  for (const t of trouvailles.slice().sort((a, b) => b.date.localeCompare(a.date))) {
    const g = groupes.find((x) => distance(x, t) <= RAYON_M);
    if (g) g.trouvailles.push(t);
    else groupes.push({ lat: t.lat, lon: t.lon, trouvailles: [t] });
  }
  return groupes;
}

/**
 * map : la carte Leaflet ; especes : règles par code ; ordre : codes dans l'ordre du site ;
 * etat() : { espece, libelle } du moment ; indiceEn(lat, lon, code) : Promise de
 * { indice, commune, protege } ou null ; decrire(indice) : { nom, couleur }.
 */
export function installerCoins({ map, especes, ordre, etat, indiceEn, decrire }) {
  const codes = new Set(ordre);
  let coins = [];
  try {
    const v = JSON.parse(localStorage.getItem(CLE) || "[]");
    coins = Array.isArray(v) ? v.filter((c) => valide(c, codes)) : [];
  } catch { coins = []; }

  const message = (texte) => { document.getElementById("coins-message").textContent = texte; };
  function sauver() {
    try {
      localStorage.setItem(CLE, JSON.stringify(coins));
      return true;
    } catch {
      message("Ce navigateur refuse de garder les coins (navigation privée ?) : ils seront perdus en fermant la page.");
      return false;
    }
  }

  const calque = L.layerGroup().addTo(map);
  const voir = document.getElementById("coins-voir");
  voir.addEventListener("change", () => (voir.checked ? calque.addTo(map) : map.removeLayer(calque)));

  // --- Ajout ------------------------------------------------------------------------
  function formulaire(latlng, precision) {
    const choix = el("select", { name: "espece" },
      ...ordre.map((c) => el("option", { value: c, selected: c === etat().espece }, especes[c].nom)));
    const date = el("input", { type: "date", name: "date", value: auJour(), max: auJour(), required: true });
    const note = el("input", { type: "text", name: "note", maxlength: "200", placeholder: "Note (facultatif)" });
    const form = el("form", { class: "coin-form" },
      el("strong", {}, "Noter une trouvaille"),
      precision ? el("p", { class: "muet" }, `Position du téléphone, à ${Math.round(precision)} m près.`) : "",
      el("label", {}, "Espèce ", choix),
      el("label", {}, "Date ", date),
      note,
      el("button", { type: "submit" }, "Enregistrer"));
    const popup = L.popup({ maxWidth: 260 }).setLatLng(latlng).setContent(form).openOn(map);
    form.addEventListener("submit", (ev) => {
      ev.preventDefault();
      if (!date.value) return;
      coins.push(propre({ id: nouvelId(), lat: latlng.lat, lon: latlng.lng, espece: choix.value,
                          date: date.value, note: note.value.trim() }));
      sauver();
      // Demande au navigateur de ne pas effacer ces données pour faire de la place.
      navigator.storage?.persist?.().catch(() => {});
      map.closePopup(popup);
      rafraichir();
    });
  }

  map.on("contextmenu", (ev) => {
    if (map.getZoom() < ZOOM_PRECIS) {
      map.setView(ev.latlng, ZOOM_PRECIS + 1);
      message("Carte rapprochée : refaites un appui long à l'endroit exact du coin.");
      return;
    }
    formulaire(ev.latlng);
  });

  document.getElementById("coin-ici").addEventListener("click", () => {
    if (!navigator.geolocation) { message("Ce navigateur ne donne pas sa position."); return; }
    message("Recherche de la position…");
    navigator.geolocation.getCurrentPosition((pos) => {
      const ll = L.latLng(pos.coords.latitude, pos.coords.longitude);
      message("");
      map.setView(ll, Math.max(map.getZoom(), 16));
      formulaire(ll, pos.coords.accuracy);
    }, (err) => {
      message(err.code === err.PERMISSION_DENIED ? "Position refusée : autorisez-la dans le navigateur, ou faites un appui long sur la carte."
        : "Position introuvable pour l'instant. Réessayez à découvert, ou faites un appui long sur la carte.");
    }, { enableHighAccuracy: true, timeout: 20000, maximumAge: 30000 });
  });

  // --- Coins sur la carte -----------------------------------------------------------
  async function bulle(groupe) {
    const t0 = groupe.trouvailles[0];
    const e = especes[t0.espece];
    const div = el("div", { class: "coin-bulle" });
    div.append(el("h4", {}, e.nom));
    const ligne = el("p", { class: "muet" }, "Indice du jour…");
    div.append(ligne);
    const ul = el("ul");
    for (const t of groupe.trouvailles) {
      ul.append(el("li", {}, dateFr(t.date), t.de ? el("span", { class: "muet" }, ` · coin de ${t.de}`) : "",
        " ", el("button", { type: "button", class: "lien", onclick: () => effacer(t) }, "effacer"),
        t.note ? el("div", { class: "muet" }, t.note) : ""));
    }
    div.append(ul);
    indiceEn(groupe.lat, groupe.lon, t0.espece).then((r) => {
      if (!r) ligne.textContent = "Hors des forêts calculées : pas d'indice.";
      else if (r.indice == null) ligne.textContent = r.protege ? "Zone protégée : pas d'indice." : "Hors forêt : pas d'indice.";
      else {
        const d = decrire(r.indice);
        ligne.replaceChildren(el("span", { class: "pastille", style: d.couleur ? `background:${d.couleur}` : "" }),
          `${majuscule(etat().libelle)} : ${d.nom.toLowerCase()}`);
      }
    }).catch((e) => { console.error(e); ligne.textContent = "L'indice n'a pas pu se calculer."; });
    return div;
  }

  function effacer(t) {
    if (!confirm(`Effacer la trouvaille du ${dateFr(t.date)} ?`)) return;
    coins = coins.filter((c) => c.id !== t.id);
    sauver();
    map.closePopup();
    rafraichir();
  }

  function dessiner(groupes) {
    calque.clearLayers();
    for (const g of groupes) {
      const partage = g.trouvailles.every((t) => t.de);
      const icone = L.divIcon({ className: `coin${partage ? " partage" : ""}`, iconSize: [24, 24],
        html: String(g.trouvailles.length > 1 ? g.trouvailles.length : especes[g.trouvailles[0].espece].nom[0]) });
      const m = L.marker([g.lat, g.lon], { icon: icone, keyboard: false, title: especes[g.trouvailles[0].espece].nom });
      m.bindPopup(() => { const d = el("div", {}, "…"); bulle(g).then((b) => d.replaceChildren(b)); return d; }, { maxWidth: 280 });
      calque.addLayer(m);
    }
  }

  // --- Panneau ----------------------------------------------------------------------
  let tour = 0;
  async function liste(groupes) {
    const ul = document.getElementById("coins-liste");
    const e = especes[etat().espece];
    const n = coins.filter((c) => c.espece === etat().espece).length;
    document.getElementById("coins-resume").textContent = coins.length
      ? `${n} trouvaille${n > 1 ? "s" : ""} de ${e.nom.toLowerCase()} sur ${coins.length} en tout.`
      : "Aucun coin noté pour l'instant.";
    ul.replaceChildren();
    if (!groupes.length) return;
    const moi = ++tour;
    const lignes = await Promise.all(groupes.map(async (g) => {
      const r = await indiceEn(g.lat, g.lon, g.trouvailles[0].espece).catch((e) => { console.error(e); return null; });
      return { g, r, v: r?.indice ?? -1 };
    }));
    if (moi !== tour) return;   // l'espèce ou le jour a changé entre-temps
    lignes.sort((a, b) => b.v - a.v);
    for (const { g, r, v } of lignes) {
      const d = v >= 0 ? decrire(v) : null;
      const annees = [...new Set(g.trouvailles.map((t) => t.date.slice(0, 4)))].sort().join(", ");
      const qui = g.trouvailles.every((t) => t.de) ? ` · ${g.trouvailles[0].de}` : "";
      ul.append(el("li", {}, el("button", { type: "button", onclick: () => map.setView([g.lat, g.lon], 15) },
        `${r?.commune ?? "Coin"} (${annees})${qui}`, el("span", { class: "cl" }, d ? d.nom : "pas d'indice"))));
    }
  }

  function sources() {
    const zone = document.getElementById("coins-sources");
    zone.replaceChildren();
    const par = new Map();
    for (const c of coins) if (c.de) par.set(c.de, (par.get(c.de) || 0) + 1);
    for (const [de, n] of par) {
      zone.append(el("li", {}, `Coins de ${de} (${n}) `, el("button", { type: "button", class: "lien", onclick: () => {
        if (!confirm(`Retirer les ${n} coins de ${de} ?`)) return;
        coins = coins.filter((c) => c.de !== de);
        sauver();
        rafraichir();
      } }, "retirer")));
    }
  }

  function rafraichir() {
    const groupes = regrouper(coins.filter((c) => c.espece === etat().espece));
    dessiner(groupes);
    sources();
    liste(groupes);
  }

  // --- Sauvegarde et partage par fichier ------------------------------------------------
  function fichier(liste, nom) {
    const doc = { format: FORMAT, version: 1, exporte_le: auJour(), coins: liste };
    return new File([JSON.stringify(doc, null, 1)], nom, { type: "application/json" });
  }
  function telecharger(f) {
    const a = el("a", { href: URL.createObjectURL(f), download: f.name });
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }

  document.getElementById("coins-sauver").addEventListener("click", () => {
    if (!coins.length) { message("Aucun coin à sauvegarder."); return; }
    telecharger(fichier(coins, `coins-champignons-${auJour()}.json`));
    message("Fichier enregistré : il contient tous les coins, les vôtres et ceux qu'on vous a confiés.");
  });

  document.getElementById("coins-partager").addEventListener("click", async () => {
    const miens = coins.filter((c) => !c.de);
    if (!miens.length) { message("Aucun coin à vous à partager."); return; }
    const f = fichier(miens, `mes-coins-champignons-${auJour()}.json`);
    if (navigator.canShare?.({ files: [f] })) {
      try { await navigator.share({ files: [f], title: "Mes coins à champignons" }); return; }
      catch (err) { if (err.name === "AbortError") return; }
    }
    telecharger(f);
    message(`${miens.length} coin${miens.length > 1 ? "s" : ""} à vous dans le fichier : envoyez-le à qui vous voulez.`);
  });

  document.getElementById("coins-importer").addEventListener("change", async (ev) => {
    const f = ev.target.files[0];
    ev.target.value = "";
    if (!f) return;
    let doc;
    try { doc = JSON.parse(await f.text()); } catch { doc = null; }
    if (doc?.format !== FORMAT || !Array.isArray(doc.coins)) {
      message("Ce fichier n'est pas un fichier de coins du site.");
      return;
    }
    const de = (prompt("De qui viennent ces coins ? Laissez vide s'il s'agit de votre propre sauvegarde.", "") ?? null);
    if (de === null) return;
    const connus = new Set(coins.map((c) => c.id));
    let ajoutes = 0, rejetes = 0;
    for (const c of doc.coins) {
      if (!valide(c, codes)) { rejetes++; continue; }
      if (connus.has(c.id)) continue;
      coins.push(propre({ ...c, de: c.de || de.trim() || null }));
      connus.add(c.id);
      ajoutes++;
    }
    sauver();
    rafraichir();
    message(`${ajoutes} coin${ajoutes > 1 ? "s" : ""} ajouté${ajoutes > 1 ? "s" : ""}` +
      (doc.coins.length - ajoutes - rejetes ? `, ${doc.coins.length - ajoutes - rejetes} déjà présent(s)` : "") +
      (rejetes ? `, ${rejetes} illisible(s)` : "") + ".");
  });

  return { rafraichir, formulaire };
}
