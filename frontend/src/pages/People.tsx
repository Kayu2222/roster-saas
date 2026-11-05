import { useState, type FormEvent } from "react";
import { api, type JobRole, type Role, type User } from "../api";
import { useSession } from "../session";
import { PageHead } from "../components/Shell";
import { Drawer, Empty, ErrorNote, Field, magnetStyle, useLoad, useSubmit, useToast } from "../components/ui";

const ROLE_LABEL: Record<Role, string> = { owner: "Owner", manager: "Manager", staff: "Staff" };

export function People() {
  const { me, canManage, hasModule } = useSession();
  const toast = useToast();
  const roster = hasModule("roster");
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<User | null>(null);

  const { data, error, reload } = useLoad(async () => {
    const users = await api<User[]>("/api/users");
    if (!roster) return { users, roles: [] as JobRole[], quals: {} as Record<string, string[]> };
    const roles = await api<JobRole[]>("/api/roster/job-roles");
    const quals = Object.fromEntries(
      await Promise.all(users.map(async (u) => [u.id, (await api<JobRole[]>(`/api/roster/staff/${u.id}/job-roles`)).map((r) => r.id)] as const)),
    );
    return { users, roles, quals };
  }, [roster]);
  const roleIds = data?.roles.map((r) => r.id) ?? [];

  return (
    <>
      <PageHead title="People" sub="Everyone in your company who can sign in.">
        {canManage && <button className="btn btn-primary" onClick={() => setAdding(true)}>Add person</button>}
      </PageHead>
      <ErrorNote error={error} />
      <section className="panel" style={{ overflowX: "auto" }}>
        {data && data.users.length > 0 ? (
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Access</th>
                {roster && <th>Works as</th>}
                {roster && canManage && <th><span className="visually-hidden">Actions</span></th>}
              </tr>
            </thead>
            <tbody>
              {data.users.map((u) => (
                <tr key={u.id}>
                  <td><strong>{u.name}</strong>{u.id === me?.user.id && <span className="muted"> (you)</span>}</td>
                  <td className="muted">{u.email}</td>
                  <td><span className="pill">{ROLE_LABEL[u.role]}</span></td>
                  {roster && (
                    <td>
                      <div className="legend">
                        {(data.quals[u.id] ?? []).map((rid) => (
                          <span key={rid} style={magnetStyle(rid, roleIds)}><i className="swatch" />{data.roles.find((r) => r.id === rid)?.name}</span>
                        ))}
                        {!(data.quals[u.id] ?? []).length && <span className="muted">Not set</span>}
                      </div>
                    </td>
                  )}
                  {roster && canManage && (
                    <td style={{ textAlign: "right" }}>
                      <button className="btn-link" onClick={() => setEditing(u)}>Edit job roles</button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          data && <Empty title="Only you so far">Add the people who work with you.</Empty>
        )}
      </section>

      {adding && (
        <AddPersonDrawer
          canAddManagers={me?.user.role === "owner"}
          onClose={() => setAdding(false)}
          onAdded={() => { setAdding(false); toast("Person added"); reload(); }}
        />
      )}
      {editing && data && (
        <JobRolesDrawer
          user={editing}
          roles={data.roles}
          current={data.quals[editing.id] ?? []}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); toast("Job roles saved"); reload(); }}
        />
      )}
    </>
  );
}

function AddPersonDrawer({ canAddManagers, onClose, onAdded }: { canAddManagers: boolean; onClose: () => void; onAdded: () => void }) {
  const { busy, error, run } = useSubmit();
  const [f, setF] = useState({ name: "", email: "", password: "", role: "staff" as Role });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    run(async () => {
      await api("/api/users", { method: "POST", body: f });
      onAdded();
    });
  };
  return (
    <Drawer title="Add person" onClose={onClose}>
      <form className="form" onSubmit={submit}>
        <ErrorNote error={error} />
        <Field label="Name"><input className="input" required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="Email"><input className="input" type="email" required value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
        <Field label="Temporary password" hint="At least 8 characters. Share it with them privately.">
          <input className="input" type="text" required minLength={8} maxLength={64} value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
        </Field>
        <Field label="Access" hint={canAddManagers ? "Managers can plan rosters and manage resources." : "Only the owner can add managers."}>
          <select className="input" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value as Role })}>
            <option value="staff">Staff: sees their own shifts and bookings</option>
            {canAddManagers && <option value="manager">Manager</option>}
          </select>
        </Field>
        <div className="form-actions">
          <button type="button" className="btn btn-quiet" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" disabled={busy}>{busy ? "Adding" : "Add person"}</button>
        </div>
      </form>
    </Drawer>
  );
}

function JobRolesDrawer({
  user, roles, current, onClose, onSaved,
}: { user: User; roles: JobRole[]; current: string[]; onClose: () => void; onSaved: () => void }) {
  const { busy, error, run } = useSubmit();
  const [picked, setPicked] = useState<string[]>(current);
  const roleIds = roles.map((r) => r.id);
  const toggle = (id: string) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  const submit = (e: FormEvent) => {
    e.preventDefault();
    run(async () => {
      await api(`/api/roster/staff/${user.id}/job-roles`, { method: "PUT", body: { job_role_ids: picked } });
      onSaved();
    });
  };
  return (
    <Drawer title={`${user.name}'s job roles`} onClose={onClose}>
      <form className="form" onSubmit={submit}>
        <ErrorNote error={error} />
        {roles.length ? (
          <div className="module-choice">
            {roles.map((r) => (
              <label key={r.id} style={magnetStyle(r.id, roleIds)}>
                <input type="checkbox" checked={picked.includes(r.id)} onChange={() => toggle(r.id)} />
                <span className="legend"><span><i className="swatch" />{r.name}</span></span>
              </label>
            ))}
          </div>
        ) : (
          <Empty title="No job roles yet">Create them under Roster, then come back.</Empty>
        )}
        <div className="form-actions">
          <button type="button" className="btn btn-quiet" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" disabled={busy || !roles.length}>{busy ? "Saving" : "Save job roles"}</button>
        </div>
      </form>
    </Drawer>
  );
}
