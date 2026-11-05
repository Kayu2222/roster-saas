import { useState, type FormEvent } from "react";
import { api, type Booking, type Client, type Resource, type ResourceType, type User } from "../api";
import { addDays, hhmm, isoDate, localDateTime, parseLocal } from "../dates";
import { useSession } from "../session";
import { PageHead } from "../components/Shell";
import { Empty, ErrorNote, Field, useLoad, useSubmit, useToast } from "../components/ui";

export function Bookings() {
  const { me, canManage } = useSession();
  const toast = useToast();
  const today = isoDate(new Date());

  const [q, setQ] = useState({ date: today, start: "09:00", end: "10:00", type: "" });
  const [purpose, setPurpose] = useState("");
  const [clientId, setClientId] = useState("");
  const [free, setFree] = useState<Resource[] | null>(null);
  const search = useSubmit();
  const book = useSubmit();

  const { data, reload } = useLoad(async () => {
    const [types, resources, users, bookings, clients] = await Promise.all([
      api<ResourceType[]>("/api/resources/types"),
      api<Resource[]>("/api/resources"),
      api<User[]>("/api/users"),
      api<Booking[]>(`/api/resources/bookings?from=${today}&to=${isoDate(addDays(new Date(), 13))}`),
      api<Client[]>("/api/clients"),
    ]);
    return { types, resources, users, bookings, clients };
  }, []);

  const window_ = () => {
    const endDate = q.end <= q.start ? isoDate(addDays(parseLocal(q.date), 1)) : q.date;
    return { start_at: localDateTime(q.date, q.start), end_at: localDateTime(endDate, q.end) };
  };

  const find = (e: FormEvent) => {
    e.preventDefault();
    search.run(async () => {
      const w = window_();
      const params = new URLSearchParams({ ...w, ...(q.type ? { type_id: q.type } : {}) });
      setFree(await api<Resource[]>(`/api/resources/availability?${params}`));
    });
  };

  const reserve = (r: Resource) =>
    book.run(async () => {
      await api("/api/resources/bookings", { method: "POST", body: { resource_id: r.id, ...window_(), purpose: purpose || null, client_id: clientId || null } });
      toast(`${r.name} booked`);
      setFree((cur) => cur?.filter((x) => x.id !== r.id) ?? null);
      reload();
    });

  const cancel = async (b: Booking) => {
    try {
      await api(`/api/resources/bookings/${b.id}/cancel`, { method: "POST" });
      toast("Booking cancelled");
      reload();
    } catch (e) {
      toast((e as Error).message);
    }
  };

  const resourceName = (id: string) => data?.resources.find((r) => r.id === id)?.name ?? "Resource";
  const who = (id: string) => (id === me?.user.id ? "You" : data?.users.find((u) => u.id === id)?.name ?? "Someone");

  return (
    <>
      <PageHead title="Bookings" sub="Find something free and book it." />
      <div className="grid-2" style={{ alignItems: "start" }}>
        <section className="panel">
          <div className="panel-head"><h2>Find a free resource</h2></div>
          <form className="panel-body form" onSubmit={find}>
            <ErrorNote error={search.error} />
            <Field label="Date"><input className="input num" type="date" required value={q.date} onChange={(e) => setQ({ ...q, date: e.target.value })} /></Field>
            <div className="form-row">
              <Field label="From"><input className="input num" type="time" required value={q.start} onChange={(e) => setQ({ ...q, start: e.target.value })} /></Field>
              <Field label="Until" hint={q.end <= q.start ? "The next day" : undefined}>
                <input className="input num" type="time" required value={q.end} onChange={(e) => setQ({ ...q, end: e.target.value })} />
              </Field>
            </div>
            <Field label="Type">
              <select className="input" value={q.type} onChange={(e) => setQ({ ...q, type: e.target.value })}>
                <option value="">Any type</option>
                {data?.types.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            </Field>
            <div className="form-actions"><button className="btn btn-primary" disabled={search.busy}>Show what's free</button></div>
          </form>

          {free && (
            <div style={{ borderTop: "1px solid var(--line)" }}>
              <div className="panel-body form" style={{ paddingBottom: 0 }}>
                <ErrorNote error={book.error} />
                <Field label="What it's for" hint="Optional, shown to managers">
                  <input className="input" maxLength={500} placeholder="For example: Team meeting" value={purpose} onChange={(e) => setPurpose(e.target.value)} />
                </Field>
                <Field label="For client" hint="Optional, for example the patient in this bed">
                  <select className="input" value={clientId} onChange={(e) => setClientId(e.target.value)}>
                    <option value="">Not for a client</option>
                    {data?.clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                  </select>
                </Field>
              </div>
              {free.length ? (
                <ul className="list">
                  {free.map((r) => (
                    <li key={r.id}>
                      <span><strong>{r.name}</strong>{r.location && <span className="muted"> {r.location}</span>}</span>
                      <button className="btn btn-primary" disabled={book.busy} onClick={() => reserve(r)}>Book {r.name}</button>
                    </li>
                  ))}
                </ul>
              ) : (
                <Empty title="Nothing free then">Try a different time or type.</Empty>
              )}
            </div>
          )}
        </section>

        <section className="panel">
          <div className="panel-head">
            <h2>{canManage ? "Next two weeks" : "Your next two weeks"}</h2>
          </div>
          {data && data.bookings.length ? (
            <ul className="list">
              {data.bookings.map((b) => (
                <li key={b.id}>
                  <span>
                    <strong>{resourceName(b.resource_id)}</strong>
                    <span className="muted num" style={{ display: "block", fontSize: "var(--fs-sm)" }}>
                      {parseLocal(b.start_at).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" })},{" "}
                      {hhmm(b.start_at)} to {hhmm(b.end_at)}
                      {canManage && `, ${who(b.booked_by)}`}
                    </span>
                    {(b.purpose || b.client_id) && (
                      <span style={{ display: "block", fontSize: "var(--fs-sm)" }}>
                        {[b.purpose, b.client_id && `for ${data.clients.find((c) => c.id === b.client_id)?.name ?? "a client"}`].filter(Boolean).join(", ")}
                      </span>
                    )}
                  </span>
                  {(canManage || b.booked_by === me?.user.id) && (
                    <button className="btn-link" onClick={() => cancel(b)}>Cancel</button>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            data && <Empty title="No bookings coming up">Use the search to book something.</Empty>
          )}
        </section>
      </div>
    </>
  );
}
