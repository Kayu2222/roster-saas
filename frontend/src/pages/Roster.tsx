import { useMemo, useState, type FormEvent } from "react";
import { NavLink } from "react-router-dom";
import { api, type JobRole, type Shift, type ShiftType, type User } from "../api";
import { addDays, dayLabel, hhmm, isoDate, localDateTime, parseLocal, rangeLabel, startOfWeek } from "../dates";
import { useSession } from "../session";
import { PageHead } from "../components/Shell";
import { Drawer, Empty, ErrorNote, Field, Icon, magnetStyle, useLoad, useSubmit, useToast } from "../components/ui";

export function RosterTabs() {
  const { canManage } = useSession();
  if (!canManage) return null;
  return (
    <nav className="tabs" aria-label="Roster">
      <NavLink to="/roster" end>Week</NavLink>
      <NavLink to="/roster/setup">Job roles and shift types</NavLink>
    </nav>
  );
}

interface RosterData {
  users: User[];
  roles: JobRole[];
  types: ShiftType[];
  shifts: Shift[];
}

export function Roster() {
  const { canManage, me } = useSession();
  const toast = useToast();
  const [weekStart, setWeekStart] = useState(() => startOfWeek(new Date()));
  const [creatingOn, setCreatingOn] = useState<string | null>(null);
  const [openShift, setOpenShift] = useState<Shift | null>(null);

  const days = useMemo(() => Array.from({ length: 7 }, (_, i) => addDays(weekStart, i)), [weekStart]);
  const from = isoDate(days[0]);
  const to = isoDate(days[6]);

  const { data, error, reload } = useLoad<RosterData>(async () => {
    const [users, roles, types, shifts] = await Promise.all([
      api<User[]>("/api/users"),
      api<JobRole[]>("/api/roster/job-roles"),
      api<ShiftType[]>("/api/roster/shift-types"),
      api<Shift[]>(`/api/roster/shifts?from=${from}&to=${to}`),
    ]);
    return { users, roles, types, shifts };
  }, [from, to]);

  const roleIds = data?.roles.map((r) => r.id) ?? [];
  const userName = (id: string) => data?.users.find((u) => u.id === id)?.name ?? "Someone";
  const roleName = (id: string | null) => data?.roles.find((r) => r.id === id)?.name;
  const today = isoDate(new Date());

  const shiftsOn = (day: string) =>
    (data?.shifts ?? [])
      .filter((s) => s.start_at.startsWith(day))
      .sort((a, b) => a.start_at.localeCompare(b.start_at));

  const removeShift = async (s: Shift) => {
    await api(`/api/roster/shifts/${s.id}`, { method: "DELETE" });
    setOpenShift(null);
    toast("Shift removed");
    reload();
  };

  return (
    <>
      <PageHead
        title="Roster"
        sub={canManage ? "Plan the week. Each colour is a job role." : "Your shifts for the week."}
      >
        <div className="segmented" role="group" aria-label="Week">
          <button aria-label="Previous week" onClick={() => setWeekStart(addDays(weekStart, -7))}><Icon name="left" /></button>
          <button aria-pressed={from <= today && today <= to} onClick={() => setWeekStart(startOfWeek(new Date()))}>This week</button>
          <button aria-label="Next week" onClick={() => setWeekStart(addDays(weekStart, 7))}><Icon name="right" /></button>
        </div>
      </PageHead>
      <RosterTabs />
      <ErrorNote error={error} />

      <div className="toolbar" style={{ justifyContent: "space-between", marginBottom: 12 }}>
        <strong className="num">{rangeLabel(days[0], days[6])}</strong>
        {data && data.roles.length > 0 && (
          <div className="legend" aria-label="Job role colours">
            {data.roles.map((r) => (
              <span key={r.id} style={magnetStyle(r.id, roleIds)}><i className="swatch" />{r.name}</span>
            ))}
          </div>
        )}
      </div>

      <div className="board">
        {days.map((d) => {
          const key = isoDate(d);
          const label = dayLabel(d);
          return (
            <section key={key} className={`day${key === today ? " today" : ""}`} aria-label={`${label.weekday} ${label.day}`}>
              <div className="day-head">
                <span className="wd">{label.weekday}</span>
                <span className="dd num">{label.day}</span>
              </div>
              <div className="day-body">
                {shiftsOn(key).map((s) => (
                  <button
                    key={s.id}
                    className="magnet"
                    style={magnetStyle(s.job_role_id, roleIds)}
                    aria-expanded={openShift?.id === s.id}
                    onClick={() => setOpenShift(s)}
                  >
                    <span className="who">{userName(s.user_id)}</span>
                    <span className="when">{hhmm(s.start_at)} to {hhmm(s.end_at)}{s.end_at.slice(0, 10) !== key ? " (+1)" : ""}</span>
                    {roleName(s.job_role_id) && <span className="role">{roleName(s.job_role_id)}</span>}
                  </button>
                ))}
                {canManage && (
                  <button className="day-add" onClick={() => setCreatingOn(key)}>
                    Add shift
                  </button>
                )}
              </div>
            </section>
          );
        })}
      </div>

      {data && data.shifts.length === 0 && !canManage && (
        <div className="panel" style={{ marginTop: 16 }}>
          <Empty title="No shifts this week">Your manager hasn't rostered you yet.</Empty>
        </div>
      )}

      {creatingOn && data && (
        <NewShiftDrawer
          date={creatingOn}
          data={data}
          onClose={() => setCreatingOn(null)}
          onCreated={() => { setCreatingOn(null); toast("Shift added"); reload(); }}
        />
      )}

      {openShift && data && (
        <Drawer title={userName(openShift.user_id)} onClose={() => setOpenShift(null)}>
          <div className="form">
            <p className="num">
              {parseLocal(openShift.start_at).toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" })}
              <br />
              {hhmm(openShift.start_at)} to {hhmm(openShift.end_at)}
            </p>
            {roleName(openShift.job_role_id) && <p>Working as {roleName(openShift.job_role_id)}</p>}
            {openShift.notes && <p className="muted">{openShift.notes}</p>}
            {canManage && (
              <div className="form-actions" style={{ justifyContent: "flex-start" }}>
                <button className="btn btn-danger" onClick={() => removeShift(openShift)}>Remove shift</button>
              </div>
            )}
            {!canManage && openShift.user_id === me?.user.id && (
              <p className="muted">Need a change? Ask your manager.</p>
            )}
          </div>
        </Drawer>
      )}
    </>
  );
}

function NewShiftDrawer({
  date, data, onClose, onCreated,
}: { date: string; data: RosterData; onClose: () => void; onCreated: () => void }) {
  const { busy, error, run } = useSubmit();
  const [mode, setMode] = useState<"template" | "custom">(data.types.length ? "template" : "custom");
  const [typeId, setTypeId] = useState(data.types[0]?.id ?? "");
  const [userId, setUserId] = useState("");
  const [start, setStart] = useState("09:00");
  const [end, setEnd] = useState("17:00");
  const [notes, setNotes] = useState("");

  const type = data.types.find((t) => t.id === typeId);
  const requiredRole = mode === "template" ? type?.job_role_id ?? null : null;
  const requiredRoleName = data.roles.find((r) => r.id === requiredRole)?.name;

  // Who holds which job role, to steer the manager away from unqualified picks.
  const quals = useLoad<Record<string, string[]>>(async () => {
    const entries = await Promise.all(
      data.users.map(async (u) => [u.id, (await api<JobRole[]>(`/api/roster/staff/${u.id}/job-roles`)).map((r) => r.id)] as const),
    );
    return Object.fromEntries(entries);
  }, []);
  const qualified = (u: User) => !requiredRole || (quals.data?.[u.id] ?? []).includes(requiredRole);
  const people = [...data.users].filter((u) => u.is_active).sort((a, b) => Number(qualified(b)) - Number(qualified(a)) || a.name.localeCompare(b.name));

  const submit = (e: FormEvent) => {
    e.preventDefault();
    run(async () => {
      let endDate = date;
      if (mode === "custom" && end <= start) endDate = isoDate(addDays(parseLocal(date), 1)); // overnight
      const body =
        mode === "template"
          ? { user_id: userId, shift_type_id: typeId, date, notes: notes || null }
          : { user_id: userId, start_at: localDateTime(date, start), end_at: localDateTime(endDate, end), notes: notes || null };
      await api("/api/roster/shifts", { method: "POST", body });
      onCreated();
    });
  };

  const dayText = parseLocal(date).toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });

  return (
    <Drawer title="Add shift" onClose={onClose}>
      <form className="form" onSubmit={submit}>
        <p className="muted">{dayText}</p>
        <ErrorNote error={error} />

        <div className="segmented" role="group" aria-label="How to set the time">
          <button type="button" aria-pressed={mode === "template"} disabled={!data.types.length} onClick={() => setMode("template")}>Use a shift type</button>
          <button type="button" aria-pressed={mode === "custom"} onClick={() => setMode("custom")}>Custom times</button>
        </div>

        {mode === "template" ? (
          <Field label="Shift type" hint={requiredRoleName ? `Only people qualified as ${requiredRoleName} can work this shift.` : undefined}>
            <select className="input" value={typeId} onChange={(e) => setTypeId(e.target.value)} required>
              {data.types.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name} ({hhmm(t.start_time)} to {hhmm(t.end_time)}{t.overnight ? ", overnight" : ""})
                </option>
              ))}
            </select>
          </Field>
        ) : (
          <div className="form-row">
            <Field label="Starts"><input className="input num" type="time" value={start} onChange={(e) => setStart(e.target.value)} required /></Field>
            <Field label="Ends" hint={end <= start ? "Ends the next day" : undefined}>
              <input className="input num" type="time" value={end} onChange={(e) => setEnd(e.target.value)} required />
            </Field>
          </div>
        )}

        <Field label="Person">
          <select className="input" value={userId} onChange={(e) => setUserId(e.target.value)} required>
            <option value="" disabled>Choose someone</option>
            {people.map((u) => (
              <option key={u.id} value={u.id} disabled={!qualified(u)}>
                {u.name}{!qualified(u) ? ` (not a ${requiredRoleName})` : ""}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Note" hint="Optional, shown on the shift">
          <input className="input" value={notes} maxLength={500} onChange={(e) => setNotes(e.target.value)} />
        </Field>

        <div className="form-actions">
          <button type="button" className="btn btn-quiet" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" disabled={busy || !userId}>{busy ? "Adding" : "Add shift"}</button>
        </div>
      </form>
    </Drawer>
  );
}
