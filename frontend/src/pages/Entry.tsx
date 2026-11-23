import { useMutation, useQueryClient } from "@tanstack/react-query";
import { QRCodeSVG } from "qrcode.react";
import { FormEvent, useState } from "react";
import {
  api, ApiError, localTime, LotSummary, money, SIZE_LABEL, tariffLine, Ticket, VEHICLE_LABEL, VEHICLE_TYPES, VehicleType,
} from "../api";
import { Card, ErrorBox, Icon, RateCardView, SizeChips, useRates, vehicleIcon } from "../ui";

export function Entry({ lot }: { lot: LotSummary }) {
  const qc = useQueryClient();
  const rates = useRates(lot.id);
  const [plate, setPlate] = useState("");
  const [vehicleType, setVehicleType] = useState<VehicleType>("CAR");
  const issue = useMutation({
    mutationFn: () => api<Ticket>(`/lots/${lot.id}/tickets`, { method: "POST", body: { plate, vehicle_type: vehicleType } }),
    onSuccess: () => {
      setPlate("");
      qc.invalidateQueries({ queryKey: ["lots"] });
      qc.invalidateQueries({ queryKey: ["occupancy", lot.id] });
    },
  });
  const submit = (e: FormEvent) => { e.preventDefault(); issue.mutate(); };
  const full = issue.error instanceof ApiError && issue.error.code === "LOT_FULL" ? issue.error.details : null;
  const rule = (vt: VehicleType) => rates.data?.rules.find((r) => r.vehicle_type === vt);
  const chosen = rule(vehicleType);

  return (
    <div className="stack">
      <SizeChips lotId={lot.id} />
      <div className="split">
        <Card title="New vehicle" sub="Type the plate as it reads; spaces and dashes are ignored." className="no-print">
          {!lot.active && (
            <div className="notice warning" style={{ marginBottom: 16 }}>
              <Icon name="power" size={16} /><span>{lot.name} is disabled, so it accepts no new vehicles. Exits still work.</span>
            </div>
          )}
          <form className="stack" onSubmit={submit}>
            <label className="field">
              Plate number
              <input className="plate-input" value={plate} onChange={(e) => setPlate(e.target.value)}
                placeholder="KA 01 AB 1234" autoFocus required autoComplete="off" spellCheck={false} disabled={!lot.active} />
            </label>
            <div className="field" role="group" aria-label="Vehicle type">
              Vehicle type
              <div className="segmented vehicle-pick">
                {VEHICLE_TYPES.map((t) => (
                  <button type="button" key={t} aria-pressed={vehicleType === t} onClick={() => setVehicleType(t)} disabled={!lot.active}>
                    <Icon name={vehicleIcon(t)} size={26} />
                    <span>{VEHICLE_LABEL[t]}</span>
                    <small>{rule(t) ? `${money(rule(t)!.hourly_rate, lot.currency)}/h` : "No rate"}</small>
                  </button>
                ))}
              </div>
            </div>
            {chosen && rates.data && (
              <p className="muted" style={{ fontSize: 13 }}>
                {tariffLine(chosen, lot.currency)}. Parks in {rates.data.compatible_sizes[vehicleType].map((s) => SIZE_LABEL[s].toLowerCase()).join(", then ")} spots.
              </p>
            )}
            <button className="btn primary lg" disabled={issue.isPending || !lot.active}>
              <Icon name="entry" />Issue ticket
            </button>
            {!full && <ErrorBox error={issue.error} />}
            {full && <LotFull lot={lot} details={full} message={issue.error!.message} />}
          </form>
        </Card>

        {issue.data ? <PrintableTicket ticket={issue.data} lot={lot} onDone={() => issue.reset()} /> : <RateCardView lot={lot} />}
      </div>
    </div>
  );
}

function LotFull({ lot, details, message }: { lot: LotSummary; details: any; message: string }) {
  return (
    <div className="notice error" role="alert" style={{ display: "grid", gap: 8 }}>
      <strong>{message}</strong>
      <span>
        Free in {lot.name} by size:{" "}
        {Object.entries(details.free_by_size as Record<string, number>).map(([s, n]) => `${s.toLowerCase()} ${n}`).join(", ") || "none"}
      </span>
      {details.alternatives.length ? (
        <span>Send the driver to {details.alternatives.map((a: any) => `${a.lot_name} (${a.free_spots} free)`).join(" or ")}.</span>
      ) : <span>No other lot in this city has a free spot for this vehicle.</span>}
    </div>
  );
}

function PrintableTicket({ ticket, lot, onDone }: { ticket: Ticket; lot: LotSummary; onDone: () => void }) {
  const rates = useRates(lot.id);
  const rule = rates.data?.rules.find((r) => r.vehicle_type === ticket.vehicle_type);
  return (
    <Card className="printable">
      <div className="ticket-card">
        <span className="pill good no-print"><Icon name="check" size={13} />Ticket issued</span>
        <h2>{lot.name}</h2>
        <div className="qr"><QRCodeSVG value={ticket.code} size={168} /></div>
        <div className="ticket-code" aria-label={`Ticket code ${ticket.code.split("").join(" ")}`}>{ticket.code}</div>
        <dl className="facts">
          <dt>Plate</dt><dd className="mono">{ticket.plate}</dd>
          <dt>Spot</dt><dd>{ticket.spot_code} · level {ticket.level_name}</dd>
          <dt>Entry</dt><dd>{localTime(ticket.entry_at, lot.timezone)}</dd>
        </dl>
        {rule && <p className="ticket-tariff">{VEHICLE_LABEL[ticket.vehicle_type]} rate: {tariffLine(rule, lot.currency)}. Lost ticket {money(rule.lost_ticket_fee, lot.currency)}.</p>}
        <div className="row no-print">
          <button className="btn primary" onClick={() => window.print()}><Icon name="printer" />Print ticket</button>
          <button className="btn" onClick={onDone}>Next vehicle</button>
        </div>
      </div>
    </Card>
  );
}
