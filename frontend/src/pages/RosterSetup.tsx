import { useState, type FormEvent } from "react";
import { api, type JobRole, type ShiftType } from "../api";
import { hhmm } from "../dates";
import { PageHead } from "../components/Shell";
import { Empty, ErrorNote, Field, magnetStyle, useLoad, useSubmit, useToast } from "../components/ui";
import { RosterTabs } from "./Roster";

export function RosterSetup() {
  const toast = useToast();
  const { data, error, reload } = useLoad(async () => {
    const [roles, types] = await Promise.all([
      api<JobRole[]>("/api/roster/job-roles"),
      api<ShiftType[]>("/api/roster/shift-types"),
    ]);
    return { roles, types };
  }, []);
  const roleIds = data?.roles.map((r) => r.id) ?? [];

  const role = useSubmit();
  const [roleName, setRoleName] = useState("");
  const addRole = (e: FormEvent) => {
    e.preventDefault();
    role.run(async () => {
      await api("/api/roster/job-roles", { method: "POST", body: { name: roleName } });
      setRoleName("");
      toast("Job role added");
      reload();
    });
  };

  const type = useSubmit();
  const [t, setT] = useState({ name: "", start_time: "07:00", end_time: "15:00", job_role_id: "" });
  const addType = (e: FormEvent) => {
    e.preventDefault();
    type.run(async () => {
      await api("/api/roster/shift-types", { method: "POST", body: { ...t, job_role_id: t.job_role_id || null } });
      setT({ ...t, name: "" });
      toast("Shift type added");
      reload();
    });
  };

  const remove = async (path: string, what: string) => {
    try {
      await api(path, { method: "DELETE" });
      toast(`${what} removed`);
      reload();
    } catch (e) {
      toast((e as Error).message);
    }
  };

  return (
    <>
      <PageHead title="Roster" sub="Set up the job roles and shift types your roster is built from." />
      <RosterTabs />
      <ErrorNote error={error} />
      <div className="grid-2">
        <section className="panel">
          <div className="panel-head"><h2>Job roles</h2></div>
          <form className="panel-body form" onSubmit={addRole}>
            <ErrorNote error={role.error} />
            <div className="toolbar">
              <input className="input" style={{ flex: 1 }} placeholder="For example: Nurse, Barista, Driver" required value={roleName} onChange={(e) => setRoleName(e.target.value)} aria-label="Job role name" />
              <button className="btn btn-primary" disabled={role.busy}>Add role</button>
            </div>
          </form>
          {data?.roles.length ? (
            <ul className="list" style={{ borderTop: "1px solid var(--line)" }}>
              {data.roles.map((r) => (
                <li key={r.id}>
                  <span style={magnetStyle(r.id, roleIds)} className="legend"><span><i className="swatch" />{r.name}</span></span>
                  <button className="btn-link" onClick={() => remove(`/api/roster/job-roles/${r.id}`, "Job role")}>Remove</button>
                </li>
              ))}
            </ul>
          ) : (
            <Empty title="No job roles yet">Add the roles people work as. Each gets its own colour on the roster.</Empty>
          )}
        </section>

        <section className="panel">
          <div className="panel-head"><h2>Shift types</h2></div>
          <form className="panel-body form" onSubmit={addType}>
            <ErrorNote error={type.error} />
            <Field label="Name">
              <input className="input" placeholder="For example: Morning" required value={t.name} onChange={(e) => setT({ ...t, name: e.target.value })} />
            </Field>
            <div className="form-row">
              <Field label="Starts"><input className="input num" type="time" required value={t.start_time} onChange={(e) => setT({ ...t, start_time: e.target.value })} /></Field>
              <Field label="Ends" hint={t.end_time <= t.start_time ? "Ends the next day" : undefined}>
                <input className="input num" type="time" required value={t.end_time} onChange={(e) => setT({ ...t, end_time: e.target.value })} />
              </Field>
            </div>
            <Field label="Who can work it" hint="Leave as anyone, or limit it to one job role">
              <select className="input" value={t.job_role_id} onChange={(e) => setT({ ...t, job_role_id: e.target.value })}>
                <option value="">Anyone</option>
                {data?.roles.map((r) => <option key={r.id} value={r.id}>{r.name} only</option>)}
              </select>
            </Field>
            <div className="form-actions"><button className="btn btn-primary" disabled={type.busy}>Add shift type</button></div>
          </form>
          {data?.types.length ? (
            <ul className="list" style={{ borderTop: "1px solid var(--line)" }}>
              {data.types.map((st) => (
                <li key={st.id}>
                  <span>
                    <strong>{st.name}</strong>{" "}
                    <span className="muted num">{hhmm(st.start_time)} to {hhmm(st.end_time)}{st.overnight ? " (overnight)" : ""}</span>
                    {st.job_role_id && <span className="pill" style={{ marginLeft: 8 }}>{data.roles.find((r) => r.id === st.job_role_id)?.name} only</span>}
                  </span>
                  <button className="btn-link" onClick={() => remove(`/api/roster/shift-types/${st.id}`, "Shift type")}>Remove</button>
                </li>
              ))}
            </ul>
          ) : (
            <Empty title="No shift types yet">Shift types are reusable times, so adding a shift takes two clicks.</Empty>
          )}
        </section>
      </div>
    </>
  );
}
