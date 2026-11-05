import { Link } from "react-router-dom";
import { api, type Booking, type JobRole, type Product, type Resource, type Shift, type User } from "../api";
import { hhmm, isoDate } from "../dates";
import { useSession } from "../session";
import { PageHead } from "../components/Shell";
import { Empty, magnetStyle, useLoad } from "../components/ui";

export function Today() {
  const { me, hasModule, canManage } = useSession();
  const roster = hasModule("roster");
  const resources = hasModule("resource");
  const inventory = hasModule("inventory");
  const today = isoDate(new Date());
  const nowLocal = `${today}T${new Date().toTimeString().slice(0, 5)}`;

  const { data } = useLoad(async () => {
    const users = await api<User[]>("/api/users");
    const [roles, shifts] = roster
      ? await Promise.all([
          api<JobRole[]>("/api/roster/job-roles"),
          api<Shift[]>(`/api/roster/shifts?from=${today}&to=${today}`),
        ])
      : [[], []];
    const [resList, bookings] = resources
      ? await Promise.all([
          api<Resource[]>("/api/resources"),
          api<Booking[]>(`/api/resources/bookings?from=${today}&to=${today}`),
        ])
      : [[], []];
    const lowStock = inventory ? await api<Product[]>("/api/inventory/products?low_only=true") : [];
    return { users, roles, shifts, resList, bookings, lowStock };
  }, [roster, resources, inventory]);

  const roleIds = data?.roles.map((r) => r.id) ?? [];
  const name = (id: string) => data?.users.find((u) => u.id === id)?.name ?? "Someone";
  const onNow = (s: { start_at: string; end_at: string }) => s.start_at <= nowLocal && nowLocal < s.end_at;
  const greeting = new Date().getHours() < 12 ? "Good morning" : new Date().getHours() < 18 ? "Good afternoon" : "Good evening";
  const dateText = new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });

  return (
    <>
      <PageHead title={`${greeting}, ${me?.user.name.split(" ")[0]}`} sub={dateText} />
      {data && data.lowStock.length > 0 && (
        <div className="notice" role="status">
          <strong>Running low:</strong> {data.lowStock.map((p) => `${p.name} (${p.on_hand} ${p.unit})`).join(", ")}.{" "}
          <Link to="/stock">Open stock</Link>
        </div>
      )}
      <div className={roster && resources ? "grid-2" : "stack"} style={{ alignItems: "start" }}>
        {roster && (
          <section className="panel">
            <div className="panel-head">
              <h2>{canManage ? "On shift today" : "Your shifts today"}</h2>
              <Link className="btn-link" to="/roster">Open roster</Link>
            </div>
            {data && data.shifts.length ? (
              <div className="panel-body" style={{ display: "grid", gap: 8 }}>
                {[...data.shifts].sort((a, b) => a.start_at.localeCompare(b.start_at)).map((s) => (
                  <div key={s.id} className="magnet" style={{ ...magnetStyle(s.job_role_id, roleIds), cursor: "default" }}>
                    <span className="who">
                      {name(s.user_id)}
                      {onNow(s) && <span className="pill" style={{ marginLeft: 8, background: "var(--marker)", color: "var(--ink)" }}>On now</span>}
                    </span>
                    <span className="when">{hhmm(s.start_at)} to {hhmm(s.end_at)}</span>
                    {s.job_role_id && <span className="role">{data.roles.find((r) => r.id === s.job_role_id)?.name}</span>}
                  </div>
                ))}
              </div>
            ) : (
              data && (
                <Empty title="Nobody is rostered today">
                  {canManage && <Link className="btn btn-primary" to="/roster">Plan the week</Link>}
                </Empty>
              )
            )}
          </section>
        )}

        {resources && (
          <section className="panel">
            <div className="panel-head">
              <h2>{canManage ? "Booked today" : "Your bookings today"}</h2>
              <Link className="btn-link" to="/bookings">Book something</Link>
            </div>
            {data && data.bookings.length ? (
              <ul className="list">
                {data.bookings.map((b) => (
                  <li key={b.id}>
                    <span>
                      <strong>{data.resList.find((r) => r.id === b.resource_id)?.name ?? "Resource"}</strong>
                      {b.purpose && <span className="muted"> {b.purpose}</span>}
                    </span>
                    <span className="num">
                      {onNow(b) && <span className="pill" style={{ marginRight: 8, background: "var(--marker)", color: "var(--ink)" }}>In use</span>}
                      {hhmm(b.start_at)} to {hhmm(b.end_at)}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              data && <Empty title="Nothing booked today" />
            )}
          </section>
        )}
      </div>
    </>
  );
}
