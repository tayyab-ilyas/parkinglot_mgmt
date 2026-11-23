import { useQuery } from "@tanstack/react-query";
import { ReactNode } from "react";
import {
  api, ApiError, LotSummary, money, OccRow, RateCard, SIZE_LABEL, SPOT_SIZES, VEHICLE_LABEL, VehicleType,
} from "./api";

const PATHS = {
  entry: "M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4M10 17l5-5-5-5M15 12H3",
  exit: "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9",
  chart: "M3 3v18h18M8 17v-5M13 17V8M18 17v-8",
  lots: "M3 21h18M5 21V8l7-5 7 5v13M9 21v-6h6v6",
  tag: "M20.6 13.4l-7.2 7.2a2 2 0 0 1-2.8 0L3 13V3h10l7.6 7.6a2 2 0 0 1 0 2.8zM7.5 7.5h.01",
  users: "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM22 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8",
  list: "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01",
  logout: "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9",
  check: "M20 6L9 17l-5-5",
  alert: "M12 9v4M12 17h.01M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z",
  info: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 16v-4M12 8h.01",
  clock: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 7v5l3 2",
  search: "M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16zM21 21l-4.3-4.3",
  printer: "M6 9V2h12v7M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2M6 14h12v8H6z",
  plus: "M12 5v14M5 12h14",
  power: "M12 2v10M18.4 6.6a9 9 0 1 1-12.8 0",
  layers: "M12 2l10 5-10 5L2 7l10-5zM2 17l10 5 10-5M2 12l10 5 10-5",
  car: "M5 17H3v-4l2.2-5.2A2 2 0 0 1 7.1 6.5h9.8a2 2 0 0 1 1.9 1.3L21 13v4h-2M3 13h18M9 17h6M7 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM17 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4z",
  motorcycle: "M5.5 20a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM18.5 20a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM5.5 16.5L9 10h6l3.5 6.5M15 10l-1.5-4H11M9 10l3 6.5",
  truck: "M1 5h13v11H1zM14 9h4l3 3.5V16h-7zM5.5 20a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM17.5 20a2 2 0 1 0 0-4 2 2 0 0 0 0 4z",
} as const;
export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75}
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={PATHS[name]} />
    </svg>
  );
}

export const vehicleIcon = (vt: VehicleType): IconName => (vt === "CAR" ? "car" : vt === "TRUCK" ? "truck" : "motorcycle");

export function VehicleTag({ vt }: { vt: VehicleType }) {
  return <span className="vt"><Icon name={vehicleIcon(vt)} />{VEHICLE_LABEL[vt]}</span>;
}

export function ErrorBox({ error }: { error: Error | null }) {
  if (!error) return null;
  const details = error instanceof ApiError && error.code === "VALIDATION_ERROR"
    ? (error.details as { loc: string[]; msg: string }[]).map((d) => `${d.loc.at(-1)}: ${d.msg}`).join("; ")
    : null;
  return (
    <div className="notice error" role="alert">
      <Icon name="alert" size={16} />
      <span>{error.message}{details && <> — {details}</>}</span>
    </div>
  );
}

export function Card({ title, sub, action, children, className = "" }: {
  title?: ReactNode; sub?: ReactNode; action?: ReactNode; children: ReactNode; className?: string;
}) {
  return (
    <section className={`card ${className}`}>
      {(title || action) && (
        <div className="card-head">
          <div>{title && <h2>{title}</h2>}{sub && <p>{sub}</p>}</div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

/** Occupancy as a status: colour + icon + words, never colour alone. */
export function occupancyStatus(occupied: number, total: number) {
  const pct = total ? occupied / total : 0;
  if (pct >= 0.9) return { level: "critical", label: total && occupied >= total ? "Full" : "Nearly full", icon: "alert" as const, pct };
  if (pct >= 0.75) return { level: "warning", label: "Filling up", icon: "clock" as const, pct };
  return { level: "good", label: "Space available", icon: "check" as const, pct };
}

export function Meter({ value, max, label }: { value: number; max: number; label: string }) {
  const s = occupancyStatus(value, max);
  return (
    <div className={`meter ${s.level === "good" ? "" : s.level}`} role="meter" aria-label={label}
      aria-valuenow={value} aria-valuemin={0} aria-valuemax={max}>
      <div style={{ width: `${Math.min(100, s.pct * 100)}%` }} />
    </div>
  );
}

export function StatusPill({ occupied, total }: { occupied: number; total: number }) {
  const s = occupancyStatus(occupied, total);
  return <span className={`pill ${s.level}`}><Icon name={s.icon} size={13} />{s.label}</span>;
}

export function LotStatePill({ active }: { active: boolean }) {
  return active
    ? <span className="pill good"><span className="dot" />Open</span>
    : <span className="pill"><Icon name="power" size={12} />Disabled</span>;
}

export const useRates = (lotId: number) =>
  useQuery({ queryKey: ["rates", lotId], queryFn: () => api<RateCard>(`/lots/${lotId}/rates`) });

export const useOccupancy = (lotId: number) =>
  useQuery({ queryKey: ["occupancy", lotId], queryFn: () => api<OccRow[]>(`/lots/${lotId}/occupancy`), refetchInterval: 5000 });

/** Free spots per size across active levels. */
export function SizeChips({ lotId }: { lotId: number }) {
  const occ = useOccupancy(lotId);
  return (
    <div className="size-chips">
      {SPOT_SIZES.map((s) => {
        const rows = occ.data?.filter((r) => r.size === s && r.level_active) ?? [];
        const total = rows.reduce((a, r) => a + r.total - r.out_of_service, 0);
        const free = rows.reduce((a, r) => a + r.free, 0);
        return (
          <div className="size-chip" key={s}>
            <span className="muted">{SIZE_LABEL[s]} spots free</span>
            <strong>{occ.data ? free : "—"}<span className="faint" style={{ fontSize: 14 }}> / {total}</span></strong>
            <Meter value={total - free} max={total} label={`${SIZE_LABEL[s]} spots in use`} />
          </div>
        );
      })}
    </div>
  );
}

/** The tariff as drivers should see it: every number that can appear on a bill. */
export function RateCardView({ lot, title = "Rate card" }: { lot: LotSummary; title?: string }) {
  const q = useRates(lot.id);
  const m = (v: number | null) => (v == null ? "No cap" : money(v, lot.currency));
  return (
    <Card title={title} sub={`${lot.name} · prices include every fee that can appear on a bill`}>
      <ErrorBox error={q.error} />
      {q.data && (q.data.rules.length ? (
        <div className="table-scroll">
          <table>
            <thead>
              <tr><th>Vehicle</th><th className="num">Free</th><th className="num">Per hour</th><th className="num">24 h cap</th><th className="num">Lost ticket</th><th>Parks in</th></tr>
            </thead>
            <tbody>
              {q.data.rules.map((r) => (
                <tr key={r.id}>
                  <td><VehicleTag vt={r.vehicle_type} /></td>
                  <td className="num">{r.free_minutes} min</td>
                  <td className="num">{money(r.hourly_rate, lot.currency)}</td>
                  <td className="num">{m(r.cap_24h)}</td>
                  <td className="num">{money(r.lost_ticket_fee, lot.currency)}</td>
                  <td className="muted">{q.data.compatible_sizes[r.vehicle_type].map((s) => SIZE_LABEL[s]).join(", then ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : <p className="muted">No pricing set for this lot yet, so entry is closed.</p>)}
      <ul className="rate-explain">
        <li><Icon name="clock" size={15} />Stays inside the free minutes cost nothing. After that, every started hour is billed from arrival.</li>
        <li><Icon name="tag" size={15} />Any 24 hours never costs more than the cap. Longer stays repeat the cap per day.</li>
        <li><Icon name="info" size={15} />The rate in force at entry applies to the whole stay, even if prices change later.</li>
      </ul>
    </Card>
  );
}
