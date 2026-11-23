import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  Analytics, api, compact, compactMoney, localDay, LotSummary, minutesLabel, MixCell, money, shortDay,
  SIZE_LABEL, VEHICLE_LABEL, VEHICLE_TYPES,
} from "../api";
import { ChartCard, ColumnChart, MixMatrix, SegmentedBar } from "../charts";
import { Card, ErrorBox, Icon, Meter, StatusPill, useOccupancy, useRates, VehicleTag } from "../ui";

const RANGES = [7, 30, 90] as const;

export function Dashboard({ lot }: { lot: LotSummary }) {
  return (
    <>
      <LiveSection lot={lot} />
      <RangeSection lot={lot} />
    </>
  );
}

function LiveSection({ lot }: { lot: LotSummary }) {
  const occ = useOccupancy(lot.id);
  const rates = useRates(lot.id);
  const parked = useQuery({ queryKey: ["parked", lot.id], queryFn: () => api<MixCell[]>(`/lots/${lot.id}/parked`), refetchInterval: 5000 });
  const rows = occ.data ?? [];
  const sum = (k: "total" | "free" | "occupied" | "out_of_service") => rows.reduce((a, r) => a + r[k], 0);
  const usable = sum("total") - sum("out_of_service");
  const byType = VEHICLE_TYPES.map((vt) => ({
    key: vt, value: (parked.data ?? []).filter((c) => c.vehicle_type === vt).reduce((a, c) => a + c.n, 0),
  }));

  return (
    <>
      <div className="section-title" style={{ marginTop: 0 }}>
        <h2>Right now</h2>
        <span className="pill good"><span className="dot" />Live · updates every 5 s</span>
      </div>
      <ErrorBox error={occ.error ?? parked.error} />
      <div className="grid cols-3">
        <Card title="Occupancy" sub={`${sum("out_of_service")} spots out of service`}>
          <div className="stat">
            <span className="value">{sum("occupied")}<span className="faint" style={{ fontSize: 18 }}> / {usable} spots</span></span>
            <Meter value={sum("occupied")} max={usable} label="Spots in use" />
            <div className="between"><StatusPill occupied={sum("occupied")} total={usable} /><span className="muted">{sum("free")} free</span></div>
          </div>
        </Card>
        <Card title="Parked by vehicle" sub="Share of vehicles in the lot now">
          <SegmentedBar parts={byType} label="Vehicles parked by type" format={(v) => `${v}`} empty="The lot is empty right now." />
        </Card>
        <Card title="Spots by size" sub="In use of usable spots">
          <div className="stack" style={{ gap: 12 }}>
            {(["SMALL", "MEDIUM", "LARGE"] as const).map((s) => {
              const r = rows.filter((x) => x.size === s);
              const u = r.reduce((a, x) => a + x.total - x.out_of_service, 0);
              const o = r.reduce((a, x) => a + x.occupied, 0);
              return (
                <div key={s} style={{ display: "grid", gap: 4 }}>
                  <div className="between"><span>{SIZE_LABEL[s]}</span><span className="muted num">{o} / {u}</span></div>
                  <Meter value={o} max={u} label={`${SIZE_LABEL[s]} spots in use`} />
                </div>
              );
            })}
          </div>
        </Card>
      </div>
      <div className="grid cols-2" style={{ marginTop: 16 }}>
        <Card title="Who is parked where" sub="Vehicles now, by type and the spot size they hold. Hatched: not allowed.">
          <MixMatrix cells={parked.data ?? []} allowed={rates.data?.compatible_sizes} />
        </Card>
        <Card title="Levels" sub="Free spots per level and size">
          <div className="table-scroll">
            <table>
              <thead><tr><th>Level</th><th>Size</th><th className="num">Free</th><th className="num">In use</th><th className="num">Out of service</th><th style={{ width: "28%" }}>Load</th></tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={`${r.level_id}-${r.size}`} className={r.level_active ? "" : "dim"}>
                    <td>{r.level_name}{!r.level_active && " (closed)"}</td><td>{SIZE_LABEL[r.size]}</td>
                    <td className="num">{r.free}</td><td className="num">{r.occupied}</td><td className="num">{r.out_of_service}</td>
                    <td><Meter value={r.occupied} max={r.total - r.out_of_service} label={`${r.level_name} ${r.size} load`} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </>
  );
}

function RangeSection({ lot }: { lot: LotSummary }) {
  const [days, setDays] = useState<(typeof RANGES)[number]>(7);
  const from = localDay(days - 1, lot.timezone);
  const to = localDay(0, lot.timezone);
  const q = useQuery({
    queryKey: ["analytics", lot.id, from, to],
    queryFn: () => api<Analytics>(`/lots/${lot.id}/analytics?from_date=${from}&to_date=${to}`),
    placeholderData: keepPreviousData,
  });
  const rates = useRates(lot.id);
  const a = q.data;
  const busy = q.isFetching && q.isPlaceholderData;
  const m = (v: number) => money(v, lot.currency);
  const cm = (v: number) => compactMoney(v, lot.currency);

  const revenue = a?.daily.reduce((s, d) => s + d.revenue, 0) ?? 0;
  const entries = a?.daily.reduce((s, d) => s + d.entries, 0) ?? 0;
  const lost = a?.by_vehicle.reduce((s, v) => s + v.lost, 0) ?? 0;
  const stays = a?.by_vehicle.reduce((s, v) => s + v.stays, 0) ?? 0;
  const avgStay = stays ? Math.round((a?.by_vehicle.reduce((s, v) => s + (v.avg_minutes ?? 0) * v.stays, 0) ?? 0) / stays) : null;
  const exits = a?.daily.reduce((s, d) => s + d.exits, 0) ?? 0;
  const peak = a?.hourly.reduce((p, h) => (h.entries > p.entries ? h : p), a.hourly[0]);
  const hh = (h: number) => `${String(h).padStart(2, "0")}:00`;
  const vehicle = (vt: string) => a?.by_vehicle.find((v) => v.vehicle_type === vt);

  return (
    <>
      <div className="section-title">
        <div><h2>Performance</h2><p>Local days in {lot.timezone}. Entries count by arrival, revenue by payment.</p></div>
        <div className="segmented compact" role="group" aria-label="Date range">
          {RANGES.map((r) => <button key={r} aria-pressed={days === r} onClick={() => setDays(r)} aria-label={`Last ${r} days`}>{r} days</button>)}
        </div>
      </div>
      <ErrorBox error={q.error} />

      <div className="stats">
        <Card className="stat hero">
          <span className="label">Revenue</span>
          <span className="value">{m(revenue)}</span>
          <span className="sub">{shortDay(from)} – {shortDay(to)}</span>
        </Card>
        <Card className="stat"><span className="label">Vehicles in</span><span className="value">{compact(entries)}</span><span className="sub">{compact(exits)} checked out</span></Card>
        <Card className="stat"><span className="label">Average stay</span><span className="value">{minutesLabel(avgStay)}</span><span className="sub">over {stays} completed stays</span></Card>
        <Card className="stat"><span className="label">Revenue per exit</span><span className="value">{exits ? m(Math.round(revenue / exits)) : "—"}</span><span className="sub">payments ÷ check-outs</span></Card>
        <Card className="stat"><span className="label">Lost tickets</span><span className="value">{lost}</span><span className="sub">{entries ? `${((lost / entries) * 100).toFixed(1)}% of entries` : "no entries"}</span></Card>
      </div>

      <div className="grid" style={{ marginTop: 16 }}>
        <ChartCard title="Revenue per day" sub={`Total ${m(revenue)}`}
          table={{ head: ["Day", "Revenue", "Vehicles in", "Checked out"], rows: (a?.daily ?? []).map((d) => [shortDay(d.day), m(d.revenue), d.entries, d.exits]) }}>
          <ColumnChart busy={busy} label="Revenue per day" format={cm} markPeak
            cols={(a?.daily ?? []).map((d) => ({
              key: d.day, label: shortDay(d.day), value: d.revenue,
              tip: <><strong>{m(d.revenue)}</strong><span className="muted">{shortDay(d.day)} · {d.entries} in, {d.exits} out</span></>,
            }))} />
        </ChartCard>

        <div className="grid cols-2">
          <ChartCard title="Vehicles in per day" sub={`${entries} entries`}
            table={{ head: ["Day", "Vehicles in"], rows: (a?.daily ?? []).map((d) => [shortDay(d.day), d.entries]) }}>
            <ColumnChart busy={busy} label="Vehicles in per day" format={(v) => compact(v)} height={200}
              cols={(a?.daily ?? []).map((d) => ({
                key: d.day, label: shortDay(d.day), value: d.entries,
                tip: <><strong>{d.entries} vehicles</strong><span className="muted">{shortDay(d.day)}</span></>,
              }))} />
          </ChartCard>
          <ChartCard title="Arrivals by hour" sub={peak && peak.entries ? `Busiest hour starts ${hh(peak.hour)}` : "No arrivals yet"}
            table={{ head: ["Hour", "Arrivals"], rows: (a?.hourly ?? []).map((h) => [hh(h.hour), h.entries]) }}>
            <ColumnChart busy={busy} label="Arrivals by hour of day" format={(v) => compact(v)} height={200} markPeak
              cols={(a?.hourly ?? []).map((h) => ({
                key: String(h.hour), label: String(h.hour).padStart(2, "0"), value: h.entries,
                tip: <><strong>{h.entries} arrivals</strong><span className="muted">{hh(h.hour)}–{hh((h.hour + 1) % 24)}</span></>,
              }))} />
          </ChartCard>
        </div>

        <div className="grid cols-2">
          <Card title="Vehicle mix" sub="Entries and revenue by vehicle type">
            <div className="stack">
              <div><p className="muted" style={{ marginBottom: 8 }}>Share of entries</p>
                <SegmentedBar parts={VEHICLE_TYPES.map((vt) => ({ key: vt, value: vehicle(vt)?.entries ?? 0 }))} label="Entries by vehicle type" format={(v) => `${v}`} /></div>
              <div><p className="muted" style={{ marginBottom: 8 }}>Share of revenue</p>
                <SegmentedBar parts={VEHICLE_TYPES.map((vt) => ({ key: vt, value: vehicle(vt)?.revenue ?? 0 }))} label="Revenue by vehicle type" format={m} /></div>
              <div className="table-scroll">
                <table>
                  <thead><tr><th>Vehicle</th><th className="num">Entries</th><th className="num">Revenue</th><th className="num">Avg stay</th><th className="num">Lost</th></tr></thead>
                  <tbody>
                    {VEHICLE_TYPES.map((vt) => {
                      const v = vehicle(vt);
                      return (
                        <tr key={vt}>
                          <td><VehicleTag vt={vt} /></td><td className="num">{v?.entries ?? 0}</td><td className="num">{m(v?.revenue ?? 0)}</td>
                          <td className="num">{minutesLabel(v?.avg_minutes)}</td><td className="num">{v?.lost ?? 0}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </Card>
          <Card title="Spot sizes used" sub="Entries in range by vehicle type and the spot size assigned. Upsized means the natural size was full.">
            <MixMatrix cells={a?.matrix ?? []} allowed={rates.data?.compatible_sizes} />
            <ul className="rate-explain">
              {VEHICLE_TYPES.map((vt) => {
                const sizes = rates.data?.compatible_sizes[vt];
                return sizes && (
                  <li key={vt}><Icon name="info" size={15} />
                    <span>{VEHICLE_LABEL[vt]}: {SIZE_LABEL[sizes[0]].toLowerCase()} first{sizes.length > 1 ? `, then ${sizes.slice(1).map((s) => SIZE_LABEL[s].toLowerCase()).join(", ")}` : ""}.</span>
                  </li>
                );
              })}
            </ul>
          </Card>
        </div>
      </div>
    </>
  );
}
