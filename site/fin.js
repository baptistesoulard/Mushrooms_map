// La carte fine (cases de 50 m) : ses couches sont publiées chiffrées (champi/chiffre.py), et
// c'est le navigateur qui les déchiffre, avec la clé tirée du mot de passe. Pas de serveur : le
// mot de passe ne quitte jamais l'appareil. La clé (pas le mot de passe) est gardée dans
// champi-carte-fine (déclarée dans a-propos.html) : on ne la redonne pas à chaque visite.
// Le lien d'accès (#fine=<clé>) l'apporte d'un toucher, pour un proche qui ne taperait pas le mot
// de passe : il le vaut, sans le dire, et cesse de marcher quand il change.
// Sans DOM ici : tests/test_chiffre.py déchiffre sous Node ce que Python a chiffré.

const CLE = "champi-carte-fine";
const texte = new TextEncoder();
const hex = (octets) => Array.from(new Uint8Array(octets), (b) => b.toString(16).padStart(2, "0")).join("");

// L'identifiant d'une clé : 12 chiffres hexadécimaux de son SHA-256, comparé à celui de
// carte.json (un mauvais mot de passe, ou un vieux lien, s'arrête là).
export async function identifier(brut) {
  return hex(await crypto.subtle.digest("SHA-256", brut)).slice(0, 12);
}

// Les octets de la clé (PBKDF2-SHA256, 32 octets), et son identifiant.
export async function deriver(motDePasse, fine) {
  const base = await crypto.subtle.importKey("raw", texte.encode(motDePasse), "PBKDF2", false, ["deriveBits"]);
  const brut = new Uint8Array(await crypto.subtle.deriveBits(
    { name: "PBKDF2", hash: "SHA-256", salt: texte.encode(fine.sel), iterations: fine.iterations }, base, 256));
  return { brut, id: await identifier(brut) };
}

export function importer(brut) {
  return crypto.subtle.importKey("raw", brut, "AES-GCM", false, ["decrypt"]);
}

// Un fichier chiffré : 12 octets de vecteur, puis le chiffré et son étiquette ; `nom` (celui du
// PNG en clair) en données associées, comme à l'aller.
export async function dechiffrer(cle, nom, contenu) {
  const o = new Uint8Array(contenu);
  return crypto.subtle.decrypt({ name: "AES-GCM", iv: o.slice(0, 12), additionalData: texte.encode(nom) },
    cle, o.slice(12));
}

// La clé gardée sur cet appareil, si elle est celle de la carte publiée : ses octets (pour
// envoyer le lien d'accès) et la clé de déchiffrement.
export async function cleGardee(fine) {
  if (!fine) return null;
  try {
    const g = JSON.parse(localStorage.getItem(CLE) || "null");
    if (!g || g.id !== fine.id) return null;
    const brut = Uint8Array.from(atob(g.cle), (c) => c.charCodeAt(0));
    return { brut, cle: await importer(brut) };
  } catch { return null; }
}

export function garder(id, brut) {
  try { localStorage.setItem(CLE, JSON.stringify({ id, cle: btoa(String.fromCharCode(...brut)) })); }
  catch { /* gardée le temps de la page */ }
}

export function oublier() {
  try { localStorage.removeItem(CLE); } catch { /* rien à retirer */ }
}

// Le lien d'accès : l'adresse de la carte, puis la clé en hexadécimal après « #fine= » (rien que
// des chiffres et des lettres : aucune messagerie ne le coupe). Ce qui suit # ne part à aucun
// serveur ; la carte le garde puis le retire de la barre d'adresse. Même format que
// champi/chiffre.py (lien).
export function lienAcces(adresse, brut) {
  return `${adresse.split("#")[0]}#fine=${hex(brut)}`;
}

// Ce que porte l'adresse après # : la clé d'un lien d'accès (son texte, ou null) et le reste (le
// lien de groupe, lu par coins.js), à remettre tel quel.
export function lireLien(hash) {
  const p = new URLSearchParams(hash.replace(/^#/, ""));
  const cle = p.get("fine");
  p.delete("fine");
  return { cle, reste: p.toString() };
}

// Les octets de la clé d'un lien, s'ils sont ceux de la carte publiée ; null sinon (lien coupé,
// ou d'avant un changement de mot de passe).
export async function cleDuLien(texteCle, fine) {
  const t = (texteCle || "").trim().toLowerCase();
  if (!fine || !/^[0-9a-f]{64}$/.test(t)) return null;
  const brut = Uint8Array.from(t.match(/../g), (h) => parseInt(h, 16));
  return (await identifier(brut)) === fine.id ? brut : null;
}
