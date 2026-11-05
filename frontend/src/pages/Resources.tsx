import { useState, type FormEvent } from "react";
import { api, type Resource, type ResourceType } from "../api";
import { useSession } from "../session";
import { PageHead } from "../components/Shell";
import { Drawer, Empty, ErrorNote, Field, useLoad, useSubmit, useToast } from "../components/ui";

export function Resources() {
  const { canManage } = useSession();
  const toast = useToast();
  const [adding, setAdding] = useState(false);
  const [addingType, setAddingType] = useState(false);

  const { data, error, reload } = useLoad(async () => {
    const [types, resources] = await Promise.all([
      api<ResourceType[]>("/api/resources/types"),
      api<Resource[]>("/api/resources"),
    ]);
    return { types, resources };
  }, []);

  const toggleService = async (r: Resource) => {
    try {
      await api(`/api/resources/${r.id}`, {
        method: "PATCH",
        body: { version: r.version, status: r.status === "available" ? "out_of_service" : "available" },
      });
      toast(r.status === "available" ? `${r.name} taken out of service` : `${r.name} back in service`);
    } catch (e) {
      toast((e as Error).message); // e.g. someone else just changed it
    }
    reload();
  };

  return (
    <>
      <PageHead title="Resources" sub="The rooms, beds, vehicles and equipment people can book.">
        {canManage && (
          <>
            <button className="btn btn-quiet" onClick={() => setAddingType(true)}>Add type</button>
            <button className="btn btn-primary" disabled={!data?.types.length} onClick={() => setAdding(true)}>Add resource</button>
          </>
        )}
      </PageHead>
      <ErrorNote error={error} />

      {data && data.types.length === 0 && (
        <section className="panel">
          <Empty title="Start with a type">
            Types group your resources, for example Meeting room, Bed or Van.
            {canManage && <button className="btn btn-primary" onClick={() => setAddingType(true)}>Add type</button>}
          </Empty>
        </section>
      )}

      <div className="stack">
        {data?.types.map((t) => {
          const items = data.resources.filter((r) => r.resource_type_id === t.id);
          return (
            <section className="panel" key={t.id}>
              <div className="panel-head">
                <h2>{t.name}</h2>
                <span className="muted">{items.length} {items.length === 1 ? "item" : "items"}</span>
              </div>
              {items.length ? (
                <ul className="list">
                  {items.map((r) => (
                    <li key={r.id}>
                      <span>
                        <strong>{r.name}</strong>
                        {r.location && <span className="muted"> {r.location}</span>}
                      </span>
                      <span className="toolbar">
                        <span className={`pill ${r.status === "available" ? "pill-ok" : "pill-off"}`}>
                          <i className="dot" />{r.status === "available" ? "In service" : "Out of service"}
                        </span>
                        {canManage && (
                          <button className="btn-link" onClick={() => toggleService(r)}>
                            {r.status === "available" ? "Take out of service" : "Put back in service"}
                          </button>
                        )}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <Empty title={`No ${t.name.toLowerCase()} yet`} />
              )}
            </section>
          );
        })}
      </div>

      {addingType && (
        <SimpleDrawer
          title="Add resource type"
          label="Type name"
          placeholder="For example: Meeting room"
          onClose={() => setAddingType(false)}
          onSubmit={async (name) => {
            await api("/api/resources/types", { method: "POST", body: { name } });
            setAddingType(false);
            toast("Type added");
            reload();
          }}
        />
      )}
      {adding && data && (
        <AddResourceDrawer
          types={data.types}
          onClose={() => setAdding(false)}
          onAdded={() => { setAdding(false); toast("Resource added"); reload(); }}
        />
      )}
    </>
  );
}

function SimpleDrawer({ title, label, placeholder, onClose, onSubmit }: {
  title: string; label: string; placeholder: string; onClose: () => void; onSubmit: (v: string) => Promise<void>;
}) {
  const { busy, error, run } = useSubmit();
  const [v, setV] = useState("");
  return (
    <Drawer title={title} onClose={onClose}>
      <form className="form" onSubmit={(e) => { e.preventDefault(); run(() => onSubmit(v)); }}>
        <ErrorNote error={error} />
        <Field label={label}><input className="input" required placeholder={placeholder} value={v} onChange={(e) => setV(e.target.value)} /></Field>
        <div className="form-actions">
          <button type="button" className="btn btn-quiet" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" disabled={busy}>{title}</button>
        </div>
      </form>
    </Drawer>
  );
}

function AddResourceDrawer({ types, onClose, onAdded }: { types: ResourceType[]; onClose: () => void; onAdded: () => void }) {
  const { busy, error, run } = useSubmit();
  const [f, setF] = useState({ resource_type_id: types[0]?.id ?? "", name: "", location: "" });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    run(async () => {
      await api("/api/resources", { method: "POST", body: { ...f, location: f.location || null } });
      onAdded();
    });
  };
  return (
    <Drawer title="Add resource" onClose={onClose}>
      <form className="form" onSubmit={submit}>
        <ErrorNote error={error} />
        <Field label="Type">
          <select className="input" value={f.resource_type_id} onChange={(e) => setF({ ...f, resource_type_id: e.target.value })}>
            {types.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
        </Field>
        <Field label="Name" hint="Must be unique, for example Room A or Van 2">
          <input className="input" required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
        </Field>
        <Field label="Location" hint="Optional">
          <input className="input" placeholder="For example: Level 2" value={f.location} onChange={(e) => setF({ ...f, location: e.target.value })} />
        </Field>
        <div className="form-actions">
          <button type="button" className="btn btn-quiet" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" disabled={busy}>{busy ? "Adding" : "Add resource"}</button>
        </div>
      </form>
    </Drawer>
  );
}
