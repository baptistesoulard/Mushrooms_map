// « Y aller » : l'itinéraire jusqu'à un point, dans l'application de son choix. Rien ne part tant
// qu'on ne touche pas un lien ; c'est alors l'application choisie qui reçoit les coordonnées du
// point (déclaré dans a-propos.html).
export function liensItineraire(lat, lon) {
  const p = `${lat.toFixed(5)},${lon.toFixed(5)}`;
  const apple = /iPhone|iPad|Macintosh/.test(navigator.userAgent);
  const liens = [
    ["Google Maps", `https://www.google.com/maps/dir/?api=1&destination=${p}`],
    ["Waze", `https://waze.com/ul?ll=${p}&navigate=yes`],
  ];
  if (apple) liens.push(["Plans", `https://maps.apple.com/?daddr=${p}`]);
  const zone = document.createElement("p");
  zone.className = "itineraire";
  zone.append(Object.assign(document.createElement("strong"), { textContent: "Y aller" }), " ");
  liens.forEach(([nom, url], k) => {
    const a = Object.assign(document.createElement("a"), { href: url, target: "_blank", rel: "noopener", textContent: nom });
    zone.append(k ? " · " : "", a);
  });
  return zone;
}
