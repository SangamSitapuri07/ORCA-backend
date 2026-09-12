/**
 * Marine navigation math — pure, client-side, offline-capable.
 * Haversine distance / initial bearing / cross-track error. There is no
 * road graph at sea, so guidance is a course line (like every real
 * chartplotter). Nothing here touches the network.
 */
export function haversineKm(aLa: number, aLo: number, bLa: number, bLo: number): number {
  const R = 6371.0;
  const p1 = (aLa * Math.PI) / 180, p2 = (bLa * Math.PI) / 180;
  const dp = ((bLa - aLa) * Math.PI) / 180, dl = ((bLo - aLo) * Math.PI) / 180;
  const a = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

export function bearingDeg(aLa: number, aLo: number, bLa: number, bLo: number): number {
  const p1 = (aLa * Math.PI) / 180, p2 = (bLa * Math.PI) / 180;
  const dl = ((bLo - aLo) * Math.PI) / 180;
  const y = Math.sin(dl) * Math.cos(p2);
  const x = Math.cos(p1) * Math.sin(p2) - Math.sin(p1) * Math.cos(p2) * Math.cos(dl);
  return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360;
}

const COMPASS16 = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];
export const compass = (d: number) => COMPASS16[Math.floor((d + 11.25) / 22.5) % 16];

/** perpendicular distance (km) from point P to segment A-B —
 *  equirectangular, jitter-level error at day-fishing distances */
export function crossTrackKm(pLa: number, pLo: number, aLa: number, aLo: number, bLa: number, bLo: number): number {
  const toXY = (la: number, lo: number) => ({
    x: (lo - aLo) * 111.32 * Math.cos((aLa * Math.PI) / 180),
    y: (la - aLa) * 110.574,
  });
  const p = toXY(pLa, pLo), b = toXY(bLa, bLo);
  const len2 = b.x * b.x + b.y * b.y;
  if (len2 < 1e-9) return Math.hypot(p.x, p.y);
  const t = Math.max(0, Math.min(1, (p.x * b.x + p.y * b.y) / len2));
  return Math.hypot(p.x - t * b.x, p.y - t * b.y);
}
