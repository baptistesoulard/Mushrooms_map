// « Que chercher ici ? » : les espèces classées pour la zone affichée, au même verdict que les
// départements (champi/redaction.niveau) : la part de la forêt à l'indice « bon » et « moyen »,
// additionnée sur les pixels de 9,2 km que touche la zone (data/vue/<jour>.png, écrit par
// champi/export_france.Vue). tests/test_ici_js.py vérifie l'accord avec Python.

// v : les octets de l'image du jour (la forêt, puis bon et moyen de chaque espèce, couche après
// couche) ; V : carte.vue ; zone : premières et dernières lignes et colonnes touchées.
export function partsZone(v, V, { l0, l1, c0, c1 }) {
  const n = V.nx * V.ny;
  let surface = 0;
  const sommes = V.especes.map(() => ({ bon: 0, moyen: 0 }));
  for (let l = Math.max(l0, 0); l <= Math.min(l1, V.ny - 1); l++) {
    for (let c = Math.max(c0, 0); c <= Math.min(c1, V.nx - 1); c++) {
      const i = l * V.nx + c;
      const s = v[i] / V.km2_par;
      if (!s) continue;
      surface += s;
      sommes.forEach((p, e) => {
        p.bon += s * v[(1 + 2 * e) * n + i];
        p.moyen += s * v[(2 + 2 * e) * n + i];
      });
    }
  }
  const parts = {};
  V.especes.forEach((code, e) => {
    parts[code] = surface ? { bon: sommes[e].bon / V.parts_par / surface, moyen: sommes[e].moyen / V.parts_par / surface }
      : { bon: 0, moyen: 0 };
  });
  return { surface, parts };
}

// Le niveau du verdict (0 hors saison … 4 bon), comme champi/redaction.niveau ; seuils de carte.json.
export function niveau(saison, bon, moyen, seuils) {
  if (saison <= 0) return 0;
  if (bon >= seuils.bon) return 4;
  if (bon >= seuils.endroits) return 3;
  if (moyen >= seuils.possible) return 2;
  return 1;
}
