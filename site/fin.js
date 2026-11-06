// La carte fine (cases de 50 m) : ses couches sont publiées chiffrées (champi/chiffre.py), et
// c'est le navigateur qui les déchiffre, avec la clé tirée du mot de passe. Pas de serveur : le
// mot de passe ne quitte jamais l'appareil. La clé (pas le mot de passe) est gardée dans
// champi-carte-fine (déclarée dans a-propos.html) : on ne la redonne pas à chaque visite.
// Sans DOM ici : tests/test_fin_js.py déchiffre sous Node ce que Python a chiffré.

const CLE = "champi-carte-fine";
const texte = new TextEncoder();
const hex = (octets) => Array.from(new Uint8Array(octets), (b) => b.toString(16).padStart(2, "0")).join("");

// Les octets de la clé (PBKDF2-SHA256, 32 octets), et son identifiant (12 chiffres hexadécimaux
// de son SHA-256), comparé à celui de carte.json : un mauvais mot de passe s'arrête là.
export async function deriver(motDePasse, fine) {
  const base = await crypto.subtle.importKey("raw", texte.encode(motDePasse), "PBKDF2", false, ["deriveBits"]);
  const brut = await crypto.subtle.deriveBits(
    { name: "PBKDF2", hash: "SHA-256", salt: texte.encode(fine.sel), iterations: fine.iterations }, base, 256);
  return { brut: new Uint8Array(brut), id: hex(await crypto.subtle.digest("SHA-256", brut)).slice(0, 12) };
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

// La clé gardée sur cet appareil, si elle est celle de la carte publiée.
export async function cleGardee(fine) {
  if (!fine) return null;
  try {
    const g = JSON.parse(localStorage.getItem(CLE) || "null");
    if (!g || g.id !== fine.id) return null;
    return await importer(Uint8Array.from(atob(g.cle), (c) => c.charCodeAt(0)));
  } catch { return null; }
}

export function garder(id, brut) {
  try { localStorage.setItem(CLE, JSON.stringify({ id, cle: btoa(String.fromCharCode(...brut)) })); }
  catch { /* gardée le temps de la page */ }
}

export function oublier() {
  try { localStorage.removeItem(CLE); } catch { /* rien à retirer */ }
}
