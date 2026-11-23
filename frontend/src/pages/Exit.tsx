import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { api, ApiError, duration, localTime, LotSummary, money, tariffLine, Ticket } from "../api";
import { Card, ErrorBox, Icon, RateCardView, VehicleTag } from "../ui";

export function Exit({ lot }: { lot: LotSummary }) {
  const [input, setInput] = useState("");
  const [code, setCode] = useState("");
  const [plate, setPlate] = useState("");
  const [lost, setLost] = useState(false);

  const lookup = (e: FormEvent) => { e.preventDefault(); setLost(false); setCode(input.trim().toUpperCase()); setInput(""); };
  const search = useQuery({
    queryKey: ["plate-search", lot.id, plate],
    queryFn: () => api<Ticket[]>(`/lots/${lot.id}/tickets?plate=${encodeURIComponent(plate)}&status=OPEN`),
    enabled: plate.replace(/[^a-z0-9]/gi, "").length >= 3,
  });

  return (
    <div className="split">
      <Card title="Find the ticket" sub="Scan the QR code, or type the 10-character code.">
        <form className="row" onSubmit={lookup}>
          <label className="field" style={{ flex: 1 }}>
            <span className="sr-only">Ticket code</span>
            <input className="code-input" value={input} onChange={(e) => setInput(e.target.value)} placeholder="e.g. VRN1P6FSCX"
              autoFocus autoComplete="off" spellCheck={false} />
          </label>
          <button className="btn primary"><Icon name="search" />Look up</button>
        </form>
        <div className="divider">Lost ticket</div>
        <label className="field">
          Search open tickets by plate
          <input value={plate} onChange={(e) => setPlate(e.target.value)} placeholder="At least 3 characters, e.g. 1234" />
        </label>
        <ErrorBox error={search.error} />
        {search.data && (search.data.length ? (
          <ul className="result-list">
            {search.data.map((t) => (
              <li key={t.code}>
                <button onClick={() => { setCode(t.code); setLost(true); }}>
                  <span><strong className="mono">{t.plate}</strong> <span className="muted">· spot {t.spot_code}</span></span>
                  <span className="muted">in since {localTime(t.entry_at, lot.timezone)}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : <p className="muted" style={{ marginTop: 12 }}>No open ticket matches that plate.</p>)}
      </Card>
      {code ? <Checkout key={code} code={code} lot={lot} lost={lost} setLost={setLost} onDone={() => setCode("")} /> : <RateCardView lot={lot} />}
    </div>
  );
}

function Checkout({ code, lot, lost, setLost, onDone }: {
  code: string; lot: LotSummary; lost: boolean; setLost: (v: boolean) => void; onDone: () => void;
}) {
  const qc = useQueryClient();
  const quote = useQuery({
    queryKey: ["ticket", code, lost],
    queryFn: () => api<Ticket>(`/tickets/${code}?lost=${lost}`),
    refetchInterval: (q) => (q.state.data?.status === "OPEN" ? 30_000 : false),
  });
  const pay = useMutation({
    mutationFn: (amount: number) => api<Ticket>(`/tickets/${code}/checkout`, { method: "POST", body: { expected_amount: amount, lost } }),
    onSuccess: () => ["lots", "plate-search", "occupancy"].forEach((k) => qc.invalidateQueries({ queryKey: [k] })),
    onError: (e) => { if (e instanceof ApiError && e.code === "FEE_CHANGED") quote.refetch(); },
  });

  if (quote.error) return <Card><ErrorBox error={quote.error} /></Card>;
  const t = quote.data;
  if (!t) return <Card><p className="muted">Looking up {code}…</p></Card>;
  const done = pay.data ?? (t.status === "CLOSED" ? t : null);

  return (
    <Card title={<span className="mono">{t.code}</span>} sub={`${t.plate} · spot ${t.spot_code}, level ${t.level_name}`}
      action={done ? <span className="pill good"><Icon name="check" size={13} />Paid</span> : <span className="pill"><span className="dot" />Parked</span>}>
      <dl className="facts">
        <dt>Vehicle</dt><dd><VehicleTag vt={t.vehicle_type} /></dd>
        <dt>Entry</dt><dd>{localTime(t.entry_at, lot.timezone)}</dd>
        <dt>Stay</dt><dd>{duration(t.entry_at, done?.exit_at)}</dd>
        {t.rule && <><dt>Tariff</dt><dd className="muted" style={{ fontWeight: 400 }}>{tariffLine(t.rule, t.currency)} · locked at entry</dd></>}
      </dl>

      <div className="receipt" aria-label="Fee breakdown">
        {t.lines?.map((line, i) => (
          <div className="line" key={i}><span>{line.label}</span><span>{money(line.amount, t.currency)}</span></div>
        ))}
        <div className="total"><span className="muted">{done ? "Paid" : "To pay now"}</span><strong>{money(done?.amount ?? t.amount, t.currency)}</strong></div>
      </div>

      {done ? (
        <div className="stack" style={{ marginTop: 16 }}>
          <div className="notice success"><Icon name="check" size={16} />
            <span>Checked out at {localTime(done.exit_at, lot.timezone)}. Spot {t.spot_code} is free again.</span></div>
          <button className="btn" onClick={onDone}>Next vehicle</button>
        </div>
      ) : (
        <div className="stack" style={{ marginTop: 16 }}>
          <label className="row" style={{ alignItems: "center", gap: 8, cursor: "pointer" }}>
            <input type="checkbox" checked={lost} onChange={(e) => setLost(e.target.checked)} style={{ width: 18, height: 18 }} />
            Driver lost the ticket (adds the lost-ticket fee)
          </label>
          <button className="btn primary lg" disabled={pay.isPending || quote.isFetching} onClick={() => pay.mutate(t.amount ?? 0)}>
            {t.amount ? `Take ${money(t.amount, t.currency)} and open exit` : "Free exit: close ticket"}
          </button>
          {pay.error instanceof ApiError && pay.error.code === "FEE_CHANGED"
            ? <div className="notice warning"><Icon name="clock" size={16} /><span>Another hour started while you waited. Check the new total and confirm again.</span></div>
            : <ErrorBox error={pay.error} />}
        </div>
      )}
    </Card>
  );
}
