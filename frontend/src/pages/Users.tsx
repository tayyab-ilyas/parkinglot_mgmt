import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { api, LotSummary, Me, Role } from "../api";
import { Card, ErrorBox } from "../ui";

export function Users() {
  const qc = useQueryClient();
  const users = useQuery({ queryKey: ["users"], queryFn: () => api<Me[]>("/users") });
  const lots = useQuery({ queryKey: ["lots"], queryFn: () => api<LotSummary[]>("/lots") });
  const refresh = () => qc.invalidateQueries({ queryKey: ["users"] });
  const [form, setForm] = useState({ username: "", password: "", role: "ATTENDANT" as Role });
  const create = useMutation({ mutationFn: () => api("/users", { method: "POST", body: form }), onSuccess: () => { refresh(); setForm({ ...form, username: "", password: "" }); } });
  const toggle = useMutation({ mutationFn: (u: Me) => api(`/users/${u.id}`, { method: "PATCH", body: { active: !u.active } }), onSuccess: refresh });
  const setLots = useMutation({
    mutationFn: ({ id, lot_ids }: { id: number; lot_ids: number[] }) => api(`/users/${id}/lots`, { method: "PUT", body: lot_ids }),
    onSuccess: refresh,
  });
  const flip = (u: Me, lotId: number) => setLots.mutate({
    id: u.id, lot_ids: u.lot_ids.includes(lotId) ? u.lot_ids.filter((x) => x !== lotId) : [...u.lot_ids, lotId],
  });
  const submit = (e: FormEvent) => { e.preventDefault(); create.mutate(); };

  return (
    <div className="stack">
      <Card title="Add a user" sub="Attendants only see the lots you tick for them. Admins see everything.">
        <form className="row" onSubmit={submit}>
          <label className="field" style={{ flex: "1 1 180px" }}>Username<input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} required minLength={3} /></label>
          <label className="field" style={{ flex: "1 1 180px" }}>Password<input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required minLength={8} placeholder="8 characters or more" /></label>
          <label className="field">Role
            <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
              <option value="ATTENDANT">Attendant</option><option value="ADMIN">Admin</option>
            </select>
          </label>
          <button className="btn primary" disabled={create.isPending}>Add user</button>
        </form>
        <div style={{ marginTop: 12 }}><ErrorBox error={create.error ?? toggle.error ?? setLots.error} /></div>
      </Card>
      <Card title="Team">
        <div className="table-scroll">
          <table>
            <thead><tr><th>User</th><th>Role</th><th>Lots</th><th>Status</th><th /></tr></thead>
            <tbody>
              {users.data?.map((u) => (
                <tr key={u.id} className={u.active ? "" : "dim"}>
                  <td><strong>{u.username}</strong></td>
                  <td>{u.role === "ADMIN" ? "Admin" : "Attendant"}</td>
                  <td>{u.role === "ADMIN" ? <span className="muted">All lots</span> : (
                    <div className="row" style={{ gap: 6 }}>
                      {lots.data?.map((l) => (
                        <label key={l.id} className={`pill${u.lot_ids.includes(l.id) ? " good" : ""}`} style={{ cursor: "pointer", minHeight: 30 }}>
                          <input type="checkbox" checked={u.lot_ids.includes(l.id)} onChange={() => flip(u, l.id)} />{l.name}
                        </label>
                      ))}
                    </div>
                  )}</td>
                  <td>{u.active ? <span className="pill good"><span className="dot" />Active</span> : <span className="pill">Deactivated</span>}</td>
                  <td><button className="btn sm" onClick={() => toggle.mutate(u)}>{u.active ? "Deactivate" : "Activate"}</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
