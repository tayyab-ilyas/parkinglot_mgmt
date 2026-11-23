export type Role = "ADMIN" | "ATTENDANT";
export type VehicleType = "MOTORCYCLE" | "CAR" | "TRUCK";
export type SpotSize = "SMALL" | "MEDIUM" | "LARGE";
export type SpotState = "FREE" | "OCCUPIED" | "OUT_OF_SERVICE";

// Fixed order everywhere: colour follows the vehicle type, never its rank.
export const VEHICLE_TYPES: VehicleType[] = ["CAR", "MOTORCYCLE", "TRUCK"];
export const SPOT_SIZES: SpotSize[] = ["SMALL", "MEDIUM", "LARGE"];
export const VEHICLE_LABEL: Record<VehicleType, string> = { CAR: "Car", MOTORCYCLE: "Motorcycle", TRUCK: "Truck" };
export const SIZE_LABEL: Record<SpotSize, string> = { SMALL: "Small", MEDIUM: "Medium", LARGE: "Large" };
export const VEHICLE_COLOR: Record<VehicleType, string> = {
  CAR: "var(--series-1)", MOTORCYCLE: "var(--series-2)", TRUCK: "var(--series-3)",
};

export interface Me { id: number; username: string; role: Role; active: boolean; lot_ids: number[] }
export interface LotSummary {
  id: number; city_id: number; city_name: string; name: string;
  timezone: string; currency: string; active: boolean; free_spots: number;
}
export interface Rule {
  id: number; vehicle_type: VehicleType; free_minutes: number; hourly_rate: number;
  cap_24h: number | null; lost_ticket_fee: number; created_at: string; retired_at?: string | null;
}
export interface RateCard { rules: Rule[]; compatible_sizes: Record<VehicleType, SpotSize[]> }
export interface FeeLine { kind: "grace" | "days" | "hours" | "lost"; label: string; amount: number; quantity?: number }
export interface Ticket {
  code: string; lot_id: number; plate: string; vehicle_type: VehicleType; spot_code: string;
  level_name: string; currency: string; entry_at: string; exit_at: string | null;
  status: "OPEN" | "CLOSED"; lost: boolean; amount?: number | null; quoted_at?: string;
  lines?: FeeLine[]; rule?: Rule;
}
export interface OccRow {
  level_id: number; level_name: string; level_active: boolean; size: SpotSize;
  total: number; free: number; occupied: number; out_of_service: number;
}
export interface MixCell { vehicle_type: VehicleType; spot_size: SpotSize; n: number }
export interface VehicleStats {
  vehicle_type: VehicleType; entries: number; lost: number; stays: number; avg_minutes: number | null; revenue: number;
}
export interface Analytics {
  daily: { day: string; entries: number; exits: number; revenue: number }[];
  hourly: { hour: number; entries: number }[];
  by_vehicle: VehicleStats[];
  matrix: MixCell[];
}
export interface LotOverview {
  lot_id: number; total_spots: number; occupied: number; out_of_service: number;
  entries_today: number; revenue_today: number;
}

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details: any) {
    super(message);
  }
}

export async function api<T>(path: string, opts: { method?: string; body?: unknown } = {}): Promise<T> {
  const hasBody = opts.body !== undefined;
  const res = await fetch(`/api${path}`, {
    method: opts.method ?? "GET",
    headers: hasBody ? { "Content-Type": "application/json" } : {},
    body: hasBody ? JSON.stringify(opts.body) : undefined,
  });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, data?.code ?? "ERROR", data?.message ?? res.statusText, data?.details);
  return data as T;
}

export const money = (minor: number | null | undefined, currency = "INR") =>
  minor == null ? "—" : new Intl.NumberFormat("en-IN", { style: "currency", currency, maximumFractionDigits: minor % 100 ? 2 : 0 }).format(minor / 100);

export const compactMoney = (minor: number, currency = "INR") =>
  new Intl.NumberFormat("en-IN", { style: "currency", currency, notation: "compact", maximumFractionDigits: 1 }).format(minor / 100);

export const compact = (n: number) => new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 }).format(n);

export const localTime = (iso: string | null, tz: string) =>
  iso ? new Date(iso).toLocaleString("en-IN", { timeZone: tz, dateStyle: "medium", timeStyle: "short" }) : "—";

export const shortDay = (isoDay: string) =>
  new Date(`${isoDay}T00:00:00Z`).toLocaleDateString("en-IN", { day: "numeric", month: "short", timeZone: "UTC" });

/** YYYY-MM-DD in the lot's timezone, `daysAgo` days before today. */
export const localDay = (daysAgo: number, tz: string) =>
  new Date(Date.now() - daysAgo * 86_400_000).toLocaleDateString("en-CA", { timeZone: tz });

export function minutesLabel(mins: number | null | undefined) {
  if (mins == null) return "—";
  return mins < 60 ? `${mins}m` : `${Math.floor(mins / 60)}h ${mins % 60}m`;
}

export const duration = (fromIso: string, toIso?: string | null) =>
  minutesLabel(Math.max(0, Math.floor(((toIso ? Date.parse(toIso) : Date.now()) - Date.parse(fromIso)) / 60000)));

/** One-line tariff, e.g. "₹40/h after 10 free min · max ₹300 per 24 h". */
export function tariffLine(rule: Rule, currency: string) {
  const parts = [`${money(rule.hourly_rate, currency)}/h${rule.free_minutes ? ` after ${rule.free_minutes} free min` : ""}`];
  if (rule.cap_24h != null) parts.push(`max ${money(rule.cap_24h, currency)} per 24 h`);
  return parts.join(" · ");
}
