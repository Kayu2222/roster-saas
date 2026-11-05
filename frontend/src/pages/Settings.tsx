import { useState } from "react";
import { api, type Module } from "../api";
import { useSession } from "../session";
import { PageHead } from "../components/Shell";
import { ErrorNote, useSubmit, useToast } from "../components/ui";

export function Settings() {
  const { me, refresh } = useSession();
  const toast = useToast();
  const { busy, error, setError, run } = useSubmit();
  const [modules, setModules] = useState<Module[]>(me?.tenant.modules ?? []);
  const isOwner = me?.user.role === "owner";

  const toggle = (m: Module) => setModules((cur) => (cur.includes(m) ? cur.filter((x) => x !== m) : [...cur, m]));
  const save = () => {
    if (!modules.length) return setError("Keep at least one feature switched on.");
    run(async () => {
      await api("/api/tenant/modules", { method: "PUT", body: { modules } });
      await refresh();
      toast("Features updated");
    });
  };

  return (
    <>
      <PageHead title={me?.tenant.name ?? "Company"} sub="Choose which features your company uses." />
      <section className="panel" style={{ maxWidth: 560 }}>
        <div className="panel-head"><h2>Features</h2></div>
        <div className="panel-body form">
          <ErrorNote error={error} />
          <div className="module-choice">
            <label>
              <input type="checkbox" disabled={!isOwner} checked={modules.includes("roster")} onChange={() => toggle("roster")} />
              <strong>Staff rosters</strong>
              <small>Job roles, shift types and the weekly roster.</small>
            </label>
            <label>
              <input type="checkbox" disabled={!isOwner} checked={modules.includes("resource")} onChange={() => toggle("resource")} />
              <strong>Resource bookings</strong>
              <small>Rooms, beds, vehicles or equipment people can book.</small>
            </label>
          </div>
          {isOwner ? (
            <div className="form-actions" style={{ justifyContent: "flex-start" }}>
              <button className="btn btn-primary" disabled={busy} onClick={save}>Save features</button>
              <span className="muted" style={{ alignSelf: "center" }}>Switching a feature off keeps its data.</span>
            </div>
          ) : (
            <p className="muted">Only the owner can change features.</p>
          )}
        </div>
      </section>
    </>
  );
}
