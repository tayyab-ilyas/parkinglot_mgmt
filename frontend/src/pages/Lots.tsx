import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { api, LotOverview, LotSummary, money, SIZE_LABEL, SPOT_SIZES, SpotSize, SpotState } from "../api";
import { Card, ErrorBox, Icon, LotStatePill, Meter, StatusPill } from "../ui";

interface City { id: number; name: string; active: boolean }
interface Level { id: number; lot_id: number; name: string; ordinal: number; active: boolean }
interface Spot { id: number; code: string; size: SpotSize; state: SpotState }

const TIMEZONES = ["Asia/Kolkata", "Asia/Dubai", "Asia/Singapore", "Europe/London", "America/New_York", "UTC"];

/** A mutation that refreshes the given query keys on success. */
function useWrite<A>(fn: (a: A) => Promise<unknown>, keys: unknown[][]) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: () => keys.forEach((k) => qc.invalidateQueries({ queryKey: k })) });
}
const post = (path: string, body?: unknown) => api(path, { method: "POST", body });
const patch = (path: string, body: unknown) => api(path, { method: "PATCH", body });

export function Lots({ onOpenLot }: { onOpenLot: (lotId: number) => void }) {
  const cities = useQuery({ queryKey: ["cities"], queryFn: () => api<City[]>("/cities") });
  const lots = useQuery({ queryKey: ["lots"], queryFn: () => api<LotSummary[]>("/lots") });
  const overview = useQuery({ queryKey: ["overview"], queryFn: () => api<LotOverview[]>("/reports/overview"), refetchInterval: 10_000 });
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<number | null>(null);
  const toggleLot = useWrite((l: LotSummary) => patch(`/lots/${l.id}`, { active: !l.active }), [["lots"], ["overview"]]);
  const toggleCity = useWrite((c: City) => patch(`/cities/${c.id}`, { active: !c.active }), [["cities"]]);

  const confirmToggle = (l: LotSummary) => {
    const msg = l.active
      ? `Disable ${l.name}? It stops taking new vehicles at once. Vehicles inside can still check out.`
      : `Enable ${l.name}? Attendants can issue tickets there again.`;
    if (window.confirm(msg)) toggleLot.mutate(l);
  };
  const totals = overview.data?.reduce((a, o) => ({ spots: a.spots + o.total_spots, occ: a.occ + o.occupied, rev: a.rev + o.revenue_today }), { spots: 0, occ: 0, rev: 0 });

  return (
    <div className="stack">
      <div className="between" style={{ flexWrap: "wrap" }}>
        <p className="muted">
          {lots.data?.length ?? 0} {lots.data?.length === 1 ? "lot" : "lots"} in {cities.data?.length ?? 0} {cities.data?.length === 1 ? "city" : "cities"}
          {totals && <> · {totals.occ} of {totals.spots} spots in use · {money(totals.rev)} taken today</>}
        </p>
        <button className="btn primary" onClick={() => setAdding(!adding)} aria-expanded={adding}><Icon name="plus" />Add lot</button>
      </div>
      {adding && <AddLot cities={cities.data ?? []} onDone={(id) => { setAdding(false); setEditing(id); }} onCancel={() => setAdding(false)} />}
      <ErrorBox error={toggleLot.error ?? toggleCity.error ?? lots.error} />

      {cities.data?.map((c) => {
        const cityLots = lots.data?.filter((l) => l.city_id === c.id) ?? [];
        return (
          <section key={c.id} className="stack" style={{ gap: 12 }}>
            <div className="section-title" style={{ margin: "12px 0 0" }}>
              <div className="row" style={{ alignItems: "center" }}>
                <h2>{c.name}</h2>
                {!c.active && <span className="pill">City retired</span>}
              </div>
              <button className="btn sm" onClick={() => toggleCity.mutate(c)}>{c.active ? "Retire city" : "Reactivate city"}</button>
            </div>
            {cityLots.length ? (
              <div className="lot-grid">
                {cityLots.map((l) => {
                  const o = overview.data?.find((x) => x.lot_id === l.id);
                  const usable = (o?.total_spots ?? 0) - (o?.out_of_service ?? 0);
                  return (
                    <article key={l.id} className={`card lot-card${l.active ? "" : " off"}`}>
                      <div className="between">
                        <div><h3 style={{ fontSize: 16 }}>{l.name}</h3><span className="muted" style={{ fontSize: 12 }}>{l.timezone} · {l.currency}</span></div>
                        <LotStatePill active={l.active} />
                      </div>
                      <div style={{ display: "grid", gap: 6 }}>
                        <div className="between">
                          {usable ? <StatusPill occupied={o?.occupied ?? 0} total={usable} /> : <span className="pill">No spots yet</span>}
                          <span className="muted num">{o?.occupied ?? 0} / {usable} in use</span>
                        </div>
                        <Meter value={o?.occupied ?? 0} max={usable} label={`${l.name} spots in use`} />
                      </div>
                      <div className="mini">
                        <div><span>Free now</span><strong>{l.free_spots}</strong></div>
                        <div><span>In today</span><strong>{o?.entries_today ?? "—"}</strong></div>
                        <div><span>Revenue today</span><strong>{o ? money(o.revenue_today, l.currency) : "—"}</strong></div>
                      </div>
                      <div className="row">
                        <button className="btn sm" onClick={() => onOpenLot(l.id)}><Icon name="chart" size={15} />Analytics</button>
                        <button className="btn sm" onClick={() => setEditing(editing === l.id ? null : l.id)} aria-expanded={editing === l.id}>
                          <Icon name="layers" size={15} />Layout
                        </button>
                        <button className={`btn sm${l.active ? " danger" : ""}`} onClick={() => confirmToggle(l)} style={{ marginLeft: "auto" }}>
                          <Icon name="power" size={15} />{l.active ? "Disable" : "Enable"}
                        </button>
                      </div>
                    </article>
                  );
                })}
              </div>
            ) : <p className="muted">No lots in {c.name} yet.</p>}
            {cityLots.some((l) => l.id === editing) && <LayoutEditor lot={cityLots.find((l) => l.id === editing)!} onClose={() => setEditing(null)} />}
          </section>
        );
      })}
    </div>
  );
}

function AddLot({ cities, onDone, onCancel }: { cities: City[]; onDone: (lotId: number) => void; onCancel: () => void }) {
  const qc = useQueryClient();
  const [cityId, setCityId] = useState<string>(cities[0] ? String(cities[0].id) : "new");
  const [cityName, setCityName] = useState("");
  const [name, setName] = useState("");
  const [timezone, setTimezone] = useState("Asia/Kolkata");
  const create = useMutation({
    mutationFn: async () => {
      const cid = cityId === "new" ? (await api<City>("/cities", { method: "POST", body: { name: cityName } })).id : Number(cityId);
      return api<{ id: number }>(`/cities/${cid}/lots`, { method: "POST", body: { name, timezone } });
    },
    onSuccess: (lot) => { ["lots", "cities", "overview"].forEach((k) => qc.invalidateQueries({ queryKey: [k] })); onDone(lot.id); },
  });
  const submit = (e: FormEvent) => { e.preventDefault(); create.mutate(); };
  return (
    <Card title="Add a lot" sub="New lots open at once. Add levels, spots and pricing before the first vehicle arrives.">
      <form className="stack" onSubmit={submit}>
        <div className="grid cols-3">
          <label className="field">City
            <select value={cityId} onChange={(e) => setCityId(e.target.value)}>
              {cities.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              <option value="new">New city…</option>
            </select>
          </label>
          {cityId === "new" && <label className="field">City name<input value={cityName} onChange={(e) => setCityName(e.target.value)} required /></label>}
          <label className="field">Lot name<input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Indiranagar" required /></label>
          <label className="field">Timezone
            <select value={timezone} onChange={(e) => setTimezone(e.target.value)}>{TIMEZONES.map((t) => <option key={t}>{t}</option>)}</select>
          </label>
        </div>
        <div className="row">
          <button className="btn primary" disabled={create.isPending}>Create lot</button>
          <button type="button" className="btn" onClick={onCancel}>Cancel</button>
        </div>
        <ErrorBox error={create.error} />
      </form>
    </Card>
  );
}

function LayoutEditor({ lot, onClose }: { lot: LotSummary; onClose: () => void }) {
  const levels = useQuery({ queryKey: ["levels", lot.id], queryFn: () => api<Level[]>(`/lots/${lot.id}/levels`) });
  const [name, setName] = useState("");
  const addLevel = useWrite(() => post(`/lots/${lot.id}/levels`, { name, ordinal: levels.data?.length ?? 0 }), [["levels", lot.id]]);
  return (
    <Card title={`Layout · ${lot.name}`} sub="Levels hold spots. Closing a level or a spot stops new vehicles going there."
      action={<button className="btn sm" onClick={onClose}>Close</button>}>
      <div className="stack">
        {levels.data?.map((lv) => <LevelRow key={lv.id} level={lv} lotId={lot.id} />)}
        {levels.data?.length === 0 && <p className="muted">No levels yet. Add the first one below.</p>}
        <form className="row" onSubmit={(e) => { e.preventDefault(); if (name.trim()) addLevel.mutate(undefined, { onSuccess: () => setName("") }); }}>
          <label className="field" style={{ flex: "1 1 200px" }}>New level<input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. B2" /></label>
          <button className="btn"><Icon name="plus" size={15} />Add level</button>
        </form>
        <ErrorBox error={addLevel.error} />
      </div>
    </Card>
  );
}

function LevelRow({ level, lotId }: { level: Level; lotId: number }) {
  const [open, setOpen] = useState(false);
  const spots = useQuery({ queryKey: ["spots", level.id], queryFn: () => api<Spot[]>(`/levels/${level.id}/spots`), enabled: open });
  const keys = [["spots", level.id], ["lots"], ["overview"], ["occupancy", lotId]];
  const toggle = useWrite(() => patch(`/levels/${level.id}`, { active: !level.active }), [["levels", lotId], ...keys]);
  const setSpot = useWrite((s: Spot) => patch(`/spots/${s.id}`, { state: s.state === "OUT_OF_SERVICE" ? "FREE" : "OUT_OF_SERVICE" }), keys);
  const addSpots = useWrite((b: object) => post(`/levels/${level.id}/spots`, b), keys);
  const [size, setSize] = useState<SpotSize>("MEDIUM");
  const [count, setCount] = useState("10");
  const [prefix, setPrefix] = useState(`${level.name}-`);
  const [start, setStart] = useState("1");

  return (
    <div className="level-row">
      <div className="between">
        <div className="row" style={{ alignItems: "center" }}>
          <strong>Level {level.name}</strong>
          {!level.active && <span className="pill">Closed</span>}
          {spots.data && <span className="muted">{spots.data.length} spots</span>}
        </div>
        <div className="row">
          <button className="btn sm" onClick={() => setOpen(!open)} aria-expanded={open}>{open ? "Hide spots" : "Show spots"}</button>
          <button className="btn sm" onClick={() => toggle.mutate(undefined)}>{level.active ? "Close level" : "Reopen level"}</button>
        </div>
      </div>
      {open && (
        <>
          <form className="row" onSubmit={(e) => { e.preventDefault(); addSpots.mutate({ size, count: Number(count), prefix, start: Number(start) }); }}>
            <label className="field">Size<select value={size} onChange={(e) => setSize(e.target.value as SpotSize)}>
              {SPOT_SIZES.map((s) => <option key={s} value={s}>{SIZE_LABEL[s]}</option>)}</select></label>
            <label className="field" style={{ width: 90 }}>Count<input type="number" min={1} max={500} value={count} onChange={(e) => setCount(e.target.value)} /></label>
            <label className="field" style={{ width: 120 }}>Code prefix<input value={prefix} onChange={(e) => setPrefix(e.target.value)} required /></label>
            <label className="field" style={{ width: 90 }}>From no.<input type="number" min={0} value={start} onChange={(e) => setStart(e.target.value)} /></label>
            <button className="btn"><Icon name="plus" size={15} />Add spots</button>
          </form>
          <ErrorBox error={addSpots.error ?? setSpot.error ?? toggle.error} />
          <div className="spots">
            {spots.data?.map((s) => (
              <button key={s.id} className={`spot ${s.state.toLowerCase()}`} disabled={s.state === "OCCUPIED"}
                title={`${SIZE_LABEL[s.size]} · ${s.state === "OUT_OF_SERVICE" ? "out of service, click to reopen" : s.state === "OCCUPIED" ? "occupied" : "free, click to take out of service"}`}
                aria-label={`${s.code}, ${SIZE_LABEL[s.size]}, ${s.state.toLowerCase().replaceAll("_", " ")}`}
                onClick={() => setSpot.mutate(s)}>
                {s.code}
              </button>
            ))}
          </div>
          <ul className="legend">
            <li><span className="swatch" style={{ background: "color-mix(in srgb, var(--good) 25%, var(--card))" }} />Free</li>
            <li><span className="swatch" style={{ background: "color-mix(in srgb, var(--critical) 30%, var(--card))" }} />Occupied</li>
            <li><span className="swatch" style={{ background: "var(--surface)" }} />Out of service</li>
          </ul>
        </>
      )}
    </div>
  );
}
