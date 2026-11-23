import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { api, localTime, LotSummary, money, Rule, tariffLine, VEHICLE_LABEL, VEHICLE_TYPES, VehicleType } from "../api";
import { Card, ErrorBox, RateCardView, VehicleTag } from "../ui";

const toMinor = (rupees: string) => (rupees === "" ? null : Math.round(Number(rupees) * 100));

export function Pricing({ lot }: { lot: LotSummary }) {
  const qc = useQueryClient();
  const key = ["pricing", lot.id];
  const history = useQuery({ queryKey: key, queryFn: () => api<Rule[]>(`/lots/${lot.id}/pricing-rules`) });
  const refresh = () => [key, ["rates", lot.id]].forEach((k) => qc.invalidateQueries({ queryKey: k }));
  const [form, setForm] = useState({ vehicle_type: "CAR" as VehicleType, free_minutes: "10", hourly: "", cap: "", lost: "0" });
  const preview: Rule | null = form.hourly ? {
    id: 0, vehicle_type: form.vehicle_type, free_minutes: Number(form.free_minutes), hourly_rate: toMinor(form.hourly) ?? 0,
    cap_24h: toMinor(form.cap), lost_ticket_fee: toMinor(form.lost) ?? 0, created_at: "",
  } : null;
  const create = useMutation({
    mutationFn: () => api(`/lots/${lot.id}/pricing-rules`, { method: "POST", body: {
      vehicle_type: form.vehicle_type, free_minutes: Number(form.free_minutes), hourly_rate: toMinor(form.hourly),
      cap_24h: toMinor(form.cap), lost_ticket_fee: toMinor(form.lost) ?? 0,
    } }),
    onSuccess: () => { refresh(); setForm({ ...form, hourly: "", cap: "" }); },
  });
  const retire = useMutation({ mutationFn: (id: number) => api(`/pricing-rules/${id}/retire`, { method: "POST" }), onSuccess: refresh });
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });
  const submit = (e: FormEvent) => { e.preventDefault(); create.mutate(); };

  return (
    <div className="stack">
      <div className="split">
        <RateCardView lot={lot} title="Rate card drivers see" />
        <Card title="Change a rate" sub="A new rate replaces the current one for that vehicle at once. Vehicles already inside keep the rate they entered under.">
          <form className="stack" onSubmit={submit}>
            <div className="grid cols-2">
              <label className="field">Vehicle
                <select value={form.vehicle_type} onChange={set("vehicle_type")}>{VEHICLE_TYPES.map((t) => <option key={t} value={t}>{VEHICLE_LABEL[t]}</option>)}</select>
              </label>
              <label className="field">Free minutes<input type="number" min={0} max={1440} value={form.free_minutes} onChange={set("free_minutes")} required /></label>
              <label className="field">Per hour ({lot.currency})<input type="number" min={0} step="0.01" value={form.hourly} onChange={set("hourly")} required /></label>
              <label className="field">24 h cap ({lot.currency})<input type="number" min={0} step="0.01" value={form.cap} onChange={set("cap")} placeholder="No cap" /></label>
              <label className="field">Lost-ticket fee ({lot.currency})<input type="number" min={0} step="0.01" value={form.lost} onChange={set("lost")} /></label>
            </div>
            {preview && <div className="notice"><span>Drivers will see: <strong>{tariffLine(preview, lot.currency)}</strong></span></div>}
            <button className="btn primary" disabled={create.isPending}>Publish new rate</button>
            <ErrorBox error={create.error ?? retire.error} />
          </form>
        </Card>
      </div>
      <Card title="Rate history" sub="Rates are never edited, only replaced or retired, so every past bill can be explained.">
        <div className="table-scroll">
          <table>
            <thead><tr><th>Vehicle</th><th>Tariff</th><th className="num">Lost fee</th><th>Published</th><th>Status</th><th /></tr></thead>
            <tbody>
              {history.data?.map((r) => (
                <tr key={r.id} className={r.retired_at ? "dim" : ""}>
                  <td><VehicleTag vt={r.vehicle_type} /></td>
                  <td>{tariffLine(r, lot.currency)}</td>
                  <td className="num">{money(r.lost_ticket_fee, lot.currency)}</td>
                  <td>{localTime(r.created_at, lot.timezone)}</td>
                  <td>{r.retired_at ? `Retired ${localTime(r.retired_at, lot.timezone)}` : <span className="pill good"><span className="dot" />Current</span>}</td>
                  <td>{!r.retired_at && (
                    <button className="btn sm danger" onClick={() => window.confirm(`Retire the ${VEHICLE_LABEL[r.vehicle_type].toLowerCase()} rate? New ${VEHICLE_LABEL[r.vehicle_type].toLowerCase()}s are refused until a new rate is published.`) && retire.mutate(r.id)}>Retire</button>
                  )}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
