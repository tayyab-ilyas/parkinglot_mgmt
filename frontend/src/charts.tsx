import { ReactNode, useLayoutEffect, useRef, useState } from "react";
import { MixCell, SIZE_LABEL, SPOT_SIZES, SpotSize, VEHICLE_COLOR, VEHICLE_LABEL, VEHICLE_TYPES, VehicleType } from "./api";
import { Card } from "./ui";

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useLayoutEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setWidth(e.contentRect.width));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, width] as const;
}

/** 1, 2, 2.5 or 5 × 10^n: clean tick steps. */
function niceStep(raw: number) {
  if (raw <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(raw));
  const n = raw / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * p;
}

/** Column with a 4px rounded data end and a square base. */
function colPath(x: number, y: number, w: number, h: number) {
  const r = Math.min(4, h, w / 2);
  return `M${x},${y + h}V${y + r}A${r},${r} 0 0 1 ${x + r},${y}H${x + w - r}A${r},${r} 0 0 1 ${x + w},${y + r}V${y + h}Z`;
}

export interface Column { key: string; label: string; value: number; tip: ReactNode }

/** Single-series column chart: one hue, recessive grid, per-column hover + focus tooltip. */
export function ColumnChart({ cols, format, label, height = 220, busy, markPeak }: {
  cols: Column[]; format: (v: number) => string; label: string; height?: number; busy?: boolean; markPeak?: boolean;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const max = Math.max(0, ...cols.map((c) => c.value));
  const step = niceStep(max / 4);
  const top = Math.max(step, Math.ceil(max / step) * step);
  const ticks = Array.from({ length: Math.round(top / step) + 1 }, (_, i) => i * step);
  const pad = { l: 56, r: 4, t: 12, b: 28 };
  const iw = Math.max(0, width - pad.l - pad.r);
  const ih = height - pad.t - pad.b;
  const band = cols.length ? iw / cols.length : 0;
  const bw = Math.min(24, band * 0.62);
  const y = (v: number) => pad.t + ih - (v / top) * ih;
  const every = Math.max(1, Math.ceil(cols.length / Math.max(1, Math.floor(iw / 46))));
  const peak = markPeak && max > 0 ? cols.findIndex((c) => c.value === max) : -1;
  const tipX = hover === null ? 0 : Math.min(Math.max(pad.l + band * hover + band / 2, 80), width - 80);

  return (
    <div className={`chart${busy ? " busy" : ""}`} ref={ref} onPointerLeave={() => setHover(null)}>
      {width > 0 && (
        <svg width={width} height={height} role="group" aria-label={label}>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={pad.l} x2={width - pad.r} y1={y(t)} y2={y(t)} className={t === 0 ? "axis-line" : "grid-line"} />
              <text x={pad.l - 10} y={y(t)} className="tick" textAnchor="end" dominantBaseline="middle">{format(t)}</text>
            </g>
          ))}
          {cols.map((c, i) => {
            const x0 = pad.l + band * i;
            const cx = x0 + band / 2;
            return (
              <g key={c.key} className={`col${hover === i ? " on" : ""}`} tabIndex={0}
                aria-label={`${c.label}: ${format(c.value)}`}
                onPointerEnter={() => setHover(i)} onFocus={() => setHover(i)} onBlur={() => setHover(null)}>
                <rect className="hit" x={x0} y={pad.t} width={band} height={ih} rx={4} />
                {c.value > 0 && <path className="bar" d={colPath(cx - bw / 2, y(c.value), bw, y(0) - y(c.value))} />}
                {i % every === 0 && (
                  <text x={cx} y={height - 8} className={`tick${i === peak ? " peak" : ""}`} textAnchor="middle">{c.label}</text>
                )}
                {i === peak && hover === null && (
                  <text x={cx} y={y(c.value) - 8} className="tick peak" textAnchor="middle">{format(c.value)}</text>
                )}
              </g>
            );
          })}
        </svg>
      )}
      {hover !== null && cols[hover] && (
        <div className="tooltip" style={{ left: tipX, top: y(cols[hover].value) }}>{cols[hover].tip}</div>
      )}
    </div>
  );
}

/** One whole split into parts: tall segmented bar with shares inside, legend in block order. */
export function SegmentedBar({ parts, label, format, empty = "Nothing recorded in this range." }: {
  parts: { key: VehicleType; value: number }[]; label: string; format: (v: number) => string; empty?: string;
}) {
  const total = parts.reduce((a, p) => a + p.value, 0);
  if (!total) return <p className="muted">{empty}</p>;
  return (
    <div>
      <div className="segbar" role="list" aria-label={label}>
        {parts.filter((p) => p.value > 0).map((p) => {
          const share = Math.round((p.value / total) * 100);
          return (
            <div key={p.key} role="listitem" tabIndex={0} className="seg" style={{ flexGrow: p.value, flexBasis: 0, background: VEHICLE_COLOR[p.key] }}
              title={`${VEHICLE_LABEL[p.key]}: ${format(p.value)} (${share}%)`} aria-label={`${VEHICLE_LABEL[p.key]}: ${format(p.value)}, ${share}%`}>
              {share >= 12 && `${share}%`}
            </div>
          );
        })}
      </div>
      <ul className="legend">
        {parts.map((p) => (
          <li key={p.key}><span className="swatch" style={{ background: VEHICLE_COLOR[p.key] }} />{VEHICLE_LABEL[p.key]} · {format(p.value)}</li>
        ))}
      </ul>
    </div>
  );
}

/** Vehicle type × spot size. One hue, light to dark by count; hatched cells are sizes that type may not use. */
export function MixMatrix({ cells, allowed }: { cells: MixCell[]; allowed?: Record<VehicleType, SpotSize[]> }) {
  const get = (vt: VehicleType, s: SpotSize) => cells.find((c) => c.vehicle_type === vt && c.spot_size === s)?.n ?? 0;
  const max = Math.max(1, ...cells.map((c) => c.n));
  return (
    <div className="table-scroll">
      <table className="matrix">
        <thead>
          <tr><th>Vehicle</th>{SPOT_SIZES.map((s) => <th key={s} style={{ textAlign: "center" }}>{SIZE_LABEL[s]}</th>)}</tr>
        </thead>
        <tbody>
          {VEHICLE_TYPES.map((vt) => (
            <tr key={vt}>
              <th scope="row"><span className="vt"><span className="swatch" style={{ background: VEHICLE_COLOR[vt] }} />{VEHICLE_LABEL[vt]}</span></th>
              {SPOT_SIZES.map((s) => {
                const sizes = allowed?.[vt];
                if (sizes && !sizes.includes(s)) return <td key={s} className="na" aria-label="Not allowed">—</td>;
                const n = get(vt, s);
                const pct = n ? 14 + Math.round((n / max) * 70) : 0;
                const upsized = sizes && n > 0 && sizes[0] !== s;
                return (
                  <td key={s} style={{
                    background: n ? `color-mix(in srgb, var(--viz-single) ${pct}%, var(--card))` : "var(--surface)",
                    color: pct > 46 ? "#fff" : "var(--ink)",
                  }}>
                    {n}
                    {upsized && <small>upsized</small>}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Card with a Chart / Table switch, so every value is reachable without hovering. */
export function ChartCard({ title, sub, table, children }: {
  title: string; sub?: string; table: { head: string[]; rows: ReactNode[][] }; children: ReactNode;
}) {
  const [asTable, setAsTable] = useState(false);
  return (
    <Card title={title} sub={sub}
      action={<button className="btn sm" onClick={() => setAsTable(!asTable)} aria-pressed={asTable}>{asTable ? "Chart" : "Table"}</button>}>
      {asTable ? (
        <div className="table-scroll" style={{ maxHeight: 260, overflowY: "auto" }}>
          <table>
            <thead><tr>{table.head.map((h, i) => <th key={h} className={i ? "num" : ""}>{h}</th>)}</tr></thead>
            <tbody>{table.rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j} className={j ? "num" : ""}>{c}</td>)}</tr>)}</tbody>
          </table>
        </div>
      ) : children}
    </Card>
  );
}
