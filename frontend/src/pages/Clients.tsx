import { useState, type FormEvent } from "react";
import { api, type ActivityItem, type Client } from "../api";
import { useSession } from "../session";
import { PageHead } from "../components/Shell";
import { Drawer, Empty, ErrorNote, Field, useLoad, useSubmit, useToast } from "../components/ui";

const NOTES_HINT = "Practical notes only, like access needs or preferred contact time. Don't record medical details.";

export function Clients() {
  const toast = useToast();
  const [q, setQ] = useState("");
  const [showArchived, setShowArchived] = useState(false);
  const [adding, setAdding] = useState(false);
  const [open, setOpen] = useState<Client | null>(null);

  const { data, error, reload } = useLoad(
    () => api<Client[]>(`/api/clients?${new URLSearchParams({ ...(q.trim() ? { q: q.trim() } : {}), include_archived: String(showArchived) })}`),
    [q, showArchived],
  );

  return (
    <>
      <PageHead title="Clients" sub="The people you serve: patients, customers, students or guests. They don't sign in.">
        <button className="btn btn-primary" onClick={() => setAdding(true)}>Add client</button>
      </PageHead>

      <div className="toolbar" style={{ marginBottom: 12 }}>
        <input className="input" style={{ maxWidth: 360 }} type="search" placeholder="Search by name, email or phone"
               aria-label="Search clients" value={q} onChange={(e) => setQ(e.target.value)} />
        <label className="toolbar muted" style={{ gap: 6 }}>
          <input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} />
          Show archived
        </label>
      </div>
      <ErrorNote error={error} />

      <section className="panel" style={{ overflowX: "auto" }}>
        {data && data.length > 0 ? (
          <table className="table">
            <thead>
              <tr><th>Name</th><th>Phone</th><th>Email</th><th><span className="visually-hidden">Open</span></th></tr>
            </thead>
            <tbody>
              {data.map((c) => (
                <tr key={c.id}>
                  <td>
                    <strong>{c.name}</strong>
                    {!c.is_active && <span className="pill" style={{ marginLeft: 8 }}>Archived</span>}
                  </td>
                  <td className="num">{c.phone ?? <span className="muted">—</span>}</td>
                  <td className="muted">{c.email ?? "—"}</td>
                  <td style={{ textAlign: "right" }}><button className="btn-link" onClick={() => setOpen(c)}>Open</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          data && (
            <Empty title={q ? `No clients match "${q}"` : "No clients yet"}>
              {!q && "Add the people you book beds, rooms or stock for."}
            </Empty>
          )
        )}
      </section>

      {adding && (
        <ClientForm
          onClose={() => setAdding(false)}
          onSaved={() => { setAdding(false); toast("Client added"); reload(); }}
        />
      )}
      {open && (
        <ClientDrawer
          client={open}
          onClose={() => setOpen(null)}
          onChanged={(msg) => { toast(msg); setOpen(null); reload(); }}
        />
      )}
    </>
  );
}

function ClientForm({ client, onClose, onSaved }: { client?: Client; onClose: () => void; onSaved: () => void }) {
  const { busy, error, run } = useSubmit();
  const [f, setF] = useState({
    name: client?.name ?? "", phone: client?.phone ?? "", email: client?.email ?? "", notes: client?.notes ?? "",
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    run(async () => {
      const body = { name: f.name, phone: f.phone || null, email: f.email || null, notes: f.notes || null };
      if (client) await api(`/api/clients/${client.id}`, { method: "PATCH", body });
      else await api("/api/clients", { method: "POST", body });
      onSaved();
    });
  };
  return (
    <Drawer title={client ? `Edit ${client.name}` : "Add client"} onClose={onClose}>
      <form className="form" onSubmit={submit}>
        <ErrorNote error={error} />
        <Field label="Name"><input className="input" required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <div className="form-row">
          <Field label="Phone"><input className="input num" type="tel" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} /></Field>
          <Field label="Email"><input className="input" type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
        </div>
        <Field label="Notes" hint={NOTES_HINT}>
          <textarea className="input" rows={3} maxLength={1000} value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} />
        </Field>
        <div className="form-actions">
          <button type="button" className="btn btn-quiet" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" disabled={busy}>{client ? "Save changes" : "Add client"}</button>
        </div>
      </form>
    </Drawer>
  );
}

function ClientDrawer({ client, onClose, onChanged }: { client: Client; onClose: () => void; onChanged: (msg: string) => void }) {
  const { canManage } = useSession();
  const [editing, setEditing] = useState(false);
  const activity = useLoad(() => api<ActivityItem[]>(`/api/clients/${client.id}/activity`), [client.id]);

  if (editing) return <ClientForm client={client} onClose={() => setEditing(false)} onSaved={() => onChanged("Client updated")} />;

  const setArchived = async (archived: boolean) => {
    await api(`/api/clients/${client.id}`, { method: "PATCH", body: { is_active: !archived } });
    onChanged(archived ? `${client.name} archived` : `${client.name} restored`);
  };

  return (
    <Drawer title={client.name} onClose={onClose}>
      <div className="form">
        <div className="muted">
          {client.phone && <div className="num">{client.phone}</div>}
          {client.email && <div>{client.email}</div>}
        </div>
        {client.notes && <p>{client.notes}</p>}
        <div className="toolbar">
          <button className="btn btn-quiet" onClick={() => setEditing(true)}>Edit details</button>
          {canManage && (client.is_active
            ? <button className="btn btn-danger" onClick={() => setArchived(true)}>Archive</button>
            : <button className="btn btn-quiet" onClick={() => setArchived(false)}>Restore</button>)}
        </div>

        <h3 style={{ fontFamily: "var(--font-display)", fontSize: "var(--fs-lg)", marginTop: 8 }}>History</h3>
        {activity.data && activity.data.length ? (
          <ul className="list panel">
            {activity.data.map((a, i) => (
              <li key={i}>
                <span>
                  <strong>{a.title}</strong>
                  <span className="muted" style={{ display: "block", fontSize: "var(--fs-sm)" }}>{a.detail}</span>
                </span>
                <span className="pill">{a.kind === "booking" ? "Booking" : "Stock used"}</span>
              </li>
            ))}
          </ul>
        ) : (
          activity.data && <p className="muted">Nothing booked or used for {client.name} yet.</p>
        )}
      </div>
    </Drawer>
  );
}
