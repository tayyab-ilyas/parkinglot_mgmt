import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useEffect, useState } from "react";
import { api, LotSummary, Me } from "./api";
import { Audit } from "./pages/Audit";
import { Dashboard } from "./pages/Dashboard";
import { Entry } from "./pages/Entry";
import { Exit } from "./pages/Exit";
import { Lots } from "./pages/Lots";
import { Pricing } from "./pages/Pricing";
import { Users } from "./pages/Users";
import { ErrorBox, Icon, IconName } from "./ui";

type Page = "entry" | "exit" | "overview" | "lots" | "pricing" | "users" | "audit";
const NAV: { id: Page; label: string; icon: IconName; admin?: boolean; lotScoped?: boolean; sub: string }[] = [
  { id: "entry", label: "Entry", icon: "entry", lotScoped: true, sub: "Issue a ticket and assign a spot" },
  { id: "exit", label: "Exit", icon: "exit", lotScoped: true, sub: "Find a ticket, take payment, free the spot" },
  { id: "overview", label: "Overview", icon: "chart", admin: true, lotScoped: true, sub: "Revenue, traffic and the vehicle mix" },
  { id: "lots", label: "Lots", icon: "lots", admin: true, sub: "Open, disable and lay out lots in every city" },
  { id: "pricing", label: "Pricing", icon: "tag", admin: true, lotScoped: true, sub: "The rates drivers pay, per vehicle type" },
  { id: "users", label: "Users", icon: "users", admin: true, sub: "Attendants, admins and the lots they work" },
  { id: "audit", label: "Audit log", icon: "list", admin: true, sub: "Every change, who made it and when" },
];

function readLot(): number | null {
  try { return Number(localStorage.getItem("lotId")) || null; } catch { return null; }
}

export function App() {
  const qc = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: () => api<Me>("/me").catch(() => null) });
  const lots = useQuery({ queryKey: ["lots"], queryFn: () => api<LotSummary[]>("/lots"), enabled: !!me.data, refetchInterval: 15_000 });
  const [page, setPage] = useState<Page | null>(null);
  const [lotId, setLotId] = useState<number | null>(readLot);

  useEffect(() => {
    if (lots.data && !lots.data.some((l) => l.id === lotId)) setLotId(lots.data[0]?.id ?? null);
  }, [lots.data, lotId]);
  useEffect(() => {
    try { if (lotId) localStorage.setItem("lotId", String(lotId)); } catch { /* storage blocked */ }
  }, [lotId]);

  const logout = useMutation({
    mutationFn: () => api("/auth/logout", { method: "POST" }),
    onSuccess: () => { qc.clear(); qc.setQueryData(["me"], null); setPage(null); },
  });

  if (me.isLoading) return null;
  if (!me.data) return <Login />;

  const isAdmin = me.data.role === "ADMIN";
  const nav = NAV.filter((n) => !n.admin || isAdmin);
  const current = nav.find((n) => n.id === (page ?? (isAdmin ? "overview" : "entry")))!;
  const lot = lots.data?.find((l) => l.id === lotId);

  return (
    <div className="shell">
      <aside className="sidebar" aria-label="Main">
        <div className="brand"><span className="brand-mark" aria-hidden="true">P</span><span>Parking Console</span></div>
        <div className="nav-group">Operate</div>
        {nav.slice(0, 2).map((n) => <NavItem key={n.id} n={n} current={current.id} onClick={() => setPage(n.id)} />)}
        {isAdmin && <div className="nav-group">Manage</div>}
        {nav.slice(2).map((n) => <NavItem key={n.id} n={n} current={current.id} onClick={() => setPage(n.id)} />)}
        <div className="sidebar-foot">
          <span className="avatar" aria-hidden="true">{me.data.username[0]}</span>
          <div className="who">{me.data.username}<br /><small>{isAdmin ? "Admin" : "Attendant"}</small></div>
          <button className="icon-btn" onClick={() => logout.mutate()} aria-label="Log out" title="Log out"><Icon name="logout" /></button>
        </div>
      </aside>

      <div>
        <header className="topbar">
          <div className="title"><h1>{current.label}</h1><p>{current.sub}</p></div>
          {current.lotScoped && (
            <label className="lot-switch">
              <span className="sr-only">Lot</span>
              <select className="input" value={lotId ?? ""} onChange={(e) => setLotId(Number(e.target.value))} aria-label="Lot">
                {lots.data?.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.name} · {l.city_name} — {l.active ? `${l.free_spots} free` : "disabled"}
                  </option>
                ))}
              </select>
            </label>
          )}
        </header>
        <main className="content" key={current.id}>
          {current.lotScoped && !lot ? (
            <div className="card empty">
              <Icon name="lots" size={28} />
              <p>{isAdmin ? "No lots yet. Add one under Lots." : "You are not assigned to a lot yet. Ask an admin to assign one."}</p>
              {isAdmin && <button className="btn primary" onClick={() => setPage("lots")}>Go to lots</button>}
            </div>
          ) : current.id === "entry" ? <Entry lot={lot!} />
            : current.id === "exit" ? <Exit lot={lot!} />
            : current.id === "overview" ? <Dashboard lot={lot!} />
            : current.id === "pricing" ? <Pricing lot={lot!} />
            : current.id === "lots" ? <Lots onOpenLot={(id) => { setLotId(id); setPage("overview"); }} />
            : current.id === "users" ? <Users />
            : <Audit />}
        </main>
      </div>
    </div>
  );
}

function NavItem({ n, current, onClick }: { n: (typeof NAV)[number]; current: Page; onClick: () => void }) {
  return (
    <button className="nav-item" aria-current={n.id === current ? "page" : undefined} onClick={onClick}>
      <Icon name={n.icon} /><span>{n.label}</span>
    </button>
  );
}

function Login() {
  const qc = useQueryClient();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const login = useMutation({
    mutationFn: () => api<Me>("/auth/login", { method: "POST", body: { username, password } }),
    onSuccess: (me) => qc.setQueryData(["me"], me),
  });
  const submit = (e: FormEvent) => { e.preventDefault(); login.mutate(); };
  return (
    <div className="login-wrap">
      <section className="login-side">
        <div className="brand"><span className="brand-mark" aria-hidden="true">P</span><span>Parking Console</span></div>
        <div>
          <h1>Paperless parking for every lot you run</h1>
          <p>Issue a ticket in one step, check vehicles out with an itemised bill, and watch every lot fill up live.</p>
        </div>
        <div className="facts-row">
          <div><strong>1 spot</strong><span>per car, enforced by the database</span></div>
          <div><strong>5 s</strong><span>between live occupancy updates</span></div>
        </div>
      </section>
      <section className="login-form">
        <form onSubmit={submit}>
          <div><h2>Log in</h2><p className="muted">Use the account your admin gave you.</p></div>
          <label className="field">Username<input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" autoFocus required /></label>
          <label className="field">Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required /></label>
          <button className="btn primary lg block" disabled={login.isPending}>Log in</button>
          <ErrorBox error={login.error} />
        </form>
      </section>
    </div>
  );
}
