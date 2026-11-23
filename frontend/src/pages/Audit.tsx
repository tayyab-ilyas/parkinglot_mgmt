import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, Me } from "../api";
import { Card, ErrorBox } from "../ui";

interface AuditRow { id: number; actor_id: number | null; action: string; entity: string; entity_id: number; data: object; at: string }
const ENTITIES = ["", "ticket", "spot", "lot", "level", "city", "pricing_rule", "user"];

export function Audit() {
  const [entity, setEntity] = useState("");
  const q = useQuery({ queryKey: ["audit", entity], queryFn: () => api<AuditRow[]>(`/audit-logs?limit=200${entity ? `&entity=${entity}` : ""}`) });
  const users = useQuery({ queryKey: ["users"], queryFn: () => api<Me[]>("/users") });
  const name = (id: number | null) => users.data?.find((u) => u.id === id)?.username ?? (id ? `#${id}` : "system");
  return (
    <Card title="Latest 200 changes" action={
      <select className="input" style={{ width: 180 }} value={entity} onChange={(e) => setEntity(e.target.value)} aria-label="Filter by entity">
        {ENTITIES.map((e) => <option key={e} value={e}>{e ? e.replace("_", " ") : "Everything"}</option>)}
      </select>
    }>
      <ErrorBox error={q.error} />
      <div className="table-scroll">
        <table>
          <thead><tr><th>When</th><th>Who</th><th>Action</th><th>Record</th><th>Details</th></tr></thead>
          <tbody>
            {q.data?.map((a) => (
              <tr key={a.id}>
                <td style={{ whiteSpace: "nowrap" }}>{new Date(a.at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}</td>
                <td>{name(a.actor_id)}</td>
                <td><span className="pill">{a.action}</span></td>
                <td className="muted">{a.entity} #{a.entity_id}</td>
                <td><code>{JSON.stringify(a.data)}</code></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
