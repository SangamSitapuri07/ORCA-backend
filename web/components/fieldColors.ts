/** Shared display colour ramps for the Explorer.
 *
 * Wave/wind breakpoints mirror ORCA's configured safety rules. Chlorophyll,
 * current, and SST colours are visual bins only and carry no ecological,
 * species, catch, or safety classification by themselves.
 */

export function chlColor(v: number): string {
  if (v >= 5) return "#ef4444";      // high display band; not a HAB diagnosis
  if (v >= 2) return "#f59e0b";
  if (v >= 0.5) return "#34d399";
  return "#64748b";
}
export function waveColor(v: number): string {
  if (v >= 4) return "#ef4444";
  if (v >= 2.5) return "#f59e0b";
  if (v >= 1.2) return "#0891b2";
  return "#38bdf8";
}
export function windColor(v: number): string {
  if (v >= 34) return "#ef4444";
  if (v >= 28) return "#f59e0b";
  if (v >= 15) return "#a78bfa";
  return "#818cf8";
}
export function currentColor(v: number): string {
  if (v >= 3) return "#ef4444";
  if (v >= 1.5) return "#f59e0b";
  if (v >= 0.6) return "#34d399";
  return "#38bdf8";
}
export function sstColor(v: number): string {
  if (v >= 30) return "#ef4444";
  if (v >= 28.5) return "#f59e0b";
  if (v >= 26) return "#34d399";
  return "#38bdf8";
}
