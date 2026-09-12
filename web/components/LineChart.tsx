"use client";

/**
 * Proper evidence chart for the advisory/Explorer — a REAL chart, not a
 * sparkline: y-axis ticks with units, time labels on x, safety threshold
 * lines (IMD/WMO small-craft limits), legend with the current value of
 * each series, and area fill. It draws the EXACT hourly arrays the
 * verdict rules read — the chart is the evidence, not an illustration.
 */

export interface ChartSeries {
  label: string;
  values: (number | null)[];
  color: string;
  dashed?: boolean;
}

export interface ChartThreshold {
  value: number;
  color: string;
  label: string;
}

function fmt(v: number, span: number): string {
  const dec = span < 5 ? 1 : 0;
  return v.toFixed(dec);
}

/** contiguous runs so missing hours render as honest gaps */
function runs(values: (number | null)[]): [number, number][][] {
  const out: [number, number][][] = [];
  let cur: [number, number][] = [];
  values.forEach((v, i) => {
    if (v == null) {
      if (cur.length) out.push(cur);
      cur = [];
    } else {
      cur.push([i, v]);
    }
  });
  if (cur.length) out.push(cur);
  return out;
}

export default function LineChart({
  series,
  labels,
  unit,
  thresholds = [],
  height = 148,
}: {
  series: ChartSeries[];
  labels: string[];
  unit: string;
  thresholds?: ChartThreshold[];
  height?: number;
}) {
  const W = 360;
  const H = height;
  const padL = 30, padR = 6, padT = 24, padB = 18;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;

  const visible = series.filter((s) => s.values.some((v) => v != null));
  const all = [
    ...visible.flatMap((s) => s.values.filter((v): v is number => v != null)),
    ...thresholds.map((t) => t.value),
  ];
  if (visible.length === 0 || all.length === 0 || labels.length < 2) {
    return <div className="text-[10px] text-slate-600 py-6 text-center">— no data —</div>;
  }

  let lo = Math.min(...all);
  let hi = Math.max(...all);
  if (hi - lo < 0.4) { lo -= 0.2; hi += 0.2; }       // avoid a dead-flat tiny range
  const pad = (hi - lo) * 0.12;
  lo -= pad; hi += pad;
  if (lo < 0 && Math.min(...all) >= 0) lo = 0;        // waves/wind can't go negative
  const span = hi - lo;

  const n = labels.length;
  const x = (i: number) => padL + (i / (n - 1)) * plotW;
  const y = (v: number) => padT + plotH - ((v - lo) / span) * plotH;

  // 4 y ticks
  const ticks = [0, 1, 2, 3].map((k) => lo + (span * k) / 3);

  // up to 5 x ticks; show HH:MM, prefix day when it changes vs previous tick
  const xIdx = Array.from(new Set([0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(f * (n - 1)))));
  const xLabel = (i: number, prev: number | null): string => {
    const s = labels[i] ?? "";
    const hm = s.slice(6, 11); // "HH:MM" from "MM-DDTHH:MM"
    const day = s.slice(3, 5); // "DD"
    if (prev != null && (labels[prev] ?? "").slice(3, 5) !== day) return `${day} ${hm}`;
    return hm;
  };

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height }}
         role="img" aria-label={`48 hour trend, ${unit}`}>
      {/* grid + y ticks */}
      {ticks.map((t, k) => (
        <g key={k}>
          <line x1={padL} x2={W - padR} y1={y(t)} y2={y(t)} stroke="#1C2A45" strokeWidth={0.6} />
          <text x={padL - 4} y={y(t) + 2.5} textAnchor="end" fontSize={7.5} fill="#64748B">
            {fmt(t, span)}
          </text>
        </g>
      ))}
      <text x={padL - 4} y={padT - 4} textAnchor="end" fontSize={7} fill="#475569">{unit}</text>

      {/* x ticks */}
      {xIdx.map((i, k) => (
        <text key={k} x={x(i)} y={H - 6} textAnchor="middle" fontSize={7.5} fill="#64748B">
          {xLabel(i, k > 0 ? xIdx[k - 1] : null)}
        </text>
      ))}

      {/* safety thresholds */}
      {thresholds.map((t, i) => (
        <g key={`th-${i}`}>
          <line x1={padL} x2={W - padR} y1={y(t.value)} y2={y(t.value)}
                stroke={t.color} strokeWidth={0.8} strokeDasharray="4 3" opacity={0.75} />
          <text x={W - padR - 1} y={y(t.value) - 2} textAnchor="end" fontSize={7} fill={t.color} opacity={0.9}>
            {t.label}
          </text>
        </g>
      ))}

      {/* area fill under first series */}
      {runs(visible[0].values).map((run, ri) => {
        if (run.length < 2) return null;
        const pts = run.map(([i, v]) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`);
        return (
          <polygon key={`a-${ri}`}
            points={`${x(run[0][0])},${y(lo)} ${pts.join(" ")} ${x(run[run.length - 1][0])},${y(lo)}`}
            fill={visible[0].color} opacity={0.12} />
        );
      })}

      {/* series lines + last-point dots */}
      {visible.map((s, si) => (
        <g key={si}>
          {runs(s.values).map((run, ri) => (
            <polyline key={ri}
              points={run.map(([i, v]) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ")}
              fill="none" stroke={s.color} strokeWidth={1.5} strokeLinejoin="round"
              strokeDasharray={s.dashed ? "3 2.5" : undefined} opacity={s.dashed ? 0.85 : 1} />
          ))}
          {(() => {
            const idxs = s.values.map((v, i) => [v, i] as const).filter(([v]) => v != null);
            if (!idxs.length) return null;
            const [v, i] = idxs[idxs.length - 1] as [number, number];
            return <circle cx={x(i)} cy={y(v)} r={2.2} fill={s.color} stroke="#0E1729" strokeWidth={0.8} />;
          })()}
        </g>
      ))}

      {/* legend with current values */}
      {visible.map((s, si) => {
        const lastV = [...s.values].reverse().find((v) => v != null) as number | undefined;
        const lx = padL + si * 118;
        return (
          <g key={`lg-${si}`}>
            <line x1={lx} x2={lx + 10} y1={9} y2={9} stroke={s.color} strokeWidth={2}
                  strokeDasharray={s.dashed ? "3 2" : undefined} />
            <text x={lx + 13} y={11.5} fontSize={8} fill="#CBD5E1">
              {s.label}
            </text>
            <text x={lx + 13 + s.label.length * 4.6 + 4} y={11.5} fontSize={8} fontWeight="bold" fill={s.color}>
              {lastV != null ? `${fmt(lastV, span)}${unit}` : "—"}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
