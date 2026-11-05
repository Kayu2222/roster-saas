import { useState, type FormEvent } from "react";
import { api, type Client, type Movement, type Product, type User } from "../api";
import { useSession } from "../session";
import { PageHead } from "../components/Shell";
import { Drawer, Empty, ErrorNote, Field, useLoad, useSubmit, useToast } from "../components/ui";

type Action = "use" | "receive" | "count";

const REASON: Record<Movement["reason"], string> = { received: "Received", used: "Used", counted: "Stocktake" };

/** A quiet level meter: how full the shelf is relative to the reorder point. */
function Level({ p }: { p: Product }) {
  const full = Math.max(p.reorder_level * 3, p.on_hand, 1);
  const pct = Math.min(100, Math.round((p.on_hand / full) * 100));
  return (
    <div className="level" aria-hidden="true">
      <div className="level-fill" style={{ width: `${pct}%`, background: p.low_stock ? "var(--danger)" : "var(--teal)" }} />
      {p.reorder_level > 0 && <div className="level-mark" style={{ left: `${Math.min(100, (p.reorder_level / full) * 100)}%` }} />}
    </div>
  );
}

export function Stock() {
  const { canManage } = useSession();
  const toast = useToast();
  const [adding, setAdding] = useState(false);
  const [acting, setActing] = useState<{ product: Product; action: Action } | null>(null);
  const [history, setHistory] = useState<Product | null>(null);

  const { data, error, reload } = useLoad(async () => {
    const [products, clients] = await Promise.all([api<Product[]>("/api/inventory/products"), api<Client[]>("/api/clients")]);
    return { products, clients };
  }, []);
  const low = data?.products.filter((p) => p.low_stock) ?? [];

  return (
    <>
      <PageHead title="Stock" sub="Medicine, supplies and anything else that gets used up.">
        {canManage && <button className="btn btn-primary" onClick={() => setAdding(true)}>Add product</button>}
      </PageHead>
      <ErrorNote error={error} />

      {low.length > 0 && (
        <div className="notice" role="status">
          <strong>Running low:</strong> {low.map((p) => `${p.name} (${p.on_hand} ${p.unit})`).join(", ")}
        </div>
      )}

      <section className="panel" style={{ overflowX: "auto" }}>
        {data && data.products.length ? (
          <table className="table">
            <thead>
              <tr><th>Product</th><th style={{ textAlign: "right" }}>On hand</th><th style={{ width: 160 }}><span className="visually-hidden">Level</span></th><th><span className="visually-hidden">Actions</span></th></tr>
            </thead>
            <tbody>
              {data.products.map((p) => (
                <tr key={p.id}>
                  <td>
                    <button className="btn-link" style={{ color: "var(--text)" }} onClick={() => setHistory(p)}>{p.name}</button>
                    {p.low_stock && <span className="pill pill-off" style={{ marginLeft: 8 }}>Low</span>}
                    {p.reorder_level > 0 && <span className="muted" style={{ display: "block", fontSize: "var(--fs-xs)" }}>Reorder at {p.reorder_level}</span>}
                  </td>
                  <td className="num" style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                    <strong style={{ fontSize: "var(--fs-lg)" }}>{p.on_hand}</strong> <span className="muted">{p.unit}</span>
                  </td>
                  <td><Level p={p} /></td>
                  <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                    <span className="toolbar" style={{ justifyContent: "flex-end" }}>
                      <button className="btn btn-quiet" disabled={p.on_hand === 0} onClick={() => setActing({ product: p, action: "use" })}>Use</button>
                      {canManage && <button className="btn btn-quiet" onClick={() => setActing({ product: p, action: "receive" })}>Receive</button>}
                      {canManage && <button className="btn-link" onClick={() => setActing({ product: p, action: "count" })}>Count</button>}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          data && <Empty title="No products yet">{canManage ? "Add what you keep in stock, with how many you have now." : "Your manager hasn't added any products yet."}</Empty>
        )}
      </section>

      {adding && <AddProduct onClose={() => setAdding(false)} onDone={() => { setAdding(false); toast("Product added"); reload(); }} />}
      {acting && data && (
        <StockAction
          {...acting}
          clients={data.clients}
          onClose={() => setActing(null)}
          onDone={(msg) => { setActing(null); toast(msg); reload(); }}
        />
      )}
      {history && data && <History product={history} clients={data.clients} onClose={() => setHistory(null)} />}
    </>
  );
}

function AddProduct({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const { busy, error, run } = useSubmit();
  const [f, setF] = useState({ name: "", unit: "box", opening_stock: 0, reorder_level: 0 });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    run(async () => {
      await api("/api/inventory/products", { method: "POST", body: f });
      onDone();
    });
  };
  return (
    <Drawer title="Add product" onClose={onClose}>
      <form className="form" onSubmit={submit}>
        <ErrorNote error={error} />
        <Field label="Name"><input className="input" required placeholder="For example: Paracetamol 500mg" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="Counted in" hint="The unit you count and use it in: box, tablet, bottle, kg">
          <input className="input" required value={f.unit} onChange={(e) => setF({ ...f, unit: e.target.value })} />
        </Field>
        <div className="form-row">
          <Field label="How many now"><input className="input num" type="number" min={0} required value={f.opening_stock} onChange={(e) => setF({ ...f, opening_stock: Number(e.target.value) })} /></Field>
          <Field label="Warn at or below"><input className="input num" type="number" min={0} required value={f.reorder_level} onChange={(e) => setF({ ...f, reorder_level: Number(e.target.value) })} /></Field>
        </div>
        <div className="form-actions">
          <button type="button" className="btn btn-quiet" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" disabled={busy}>Add product</button>
        </div>
      </form>
    </Drawer>
  );
}

function StockAction({ product, action, clients, onClose, onDone }: {
  product: Product; action: Action; clients: Client[]; onClose: () => void; onDone: (msg: string) => void;
}) {
  const { busy, error, run } = useSubmit();
  const [qty, setQty] = useState(action === "count" ? product.on_hand : 1);
  const [clientId, setClientId] = useState("");
  const [note, setNote] = useState("");
  const title = { use: `Use ${product.name}`, receive: `Receive ${product.name}`, count: `Count ${product.name}` }[action];

  const submit = (e: FormEvent) => {
    e.preventDefault();
    run(async () => {
      const path = `/api/inventory/products/${product.id}/${action}`;
      if (action === "count") await api(path, { method: "POST", body: { counted: qty, expected: product.on_hand, note: note || null } });
      else if (action === "use") await api(path, { method: "POST", body: { quantity: qty, client_id: clientId || null, note: note || null } });
      else await api(path, { method: "POST", body: { quantity: qty, note: note || null } });
      onDone(action === "use" ? `Used ${qty} ${product.unit}` : action === "receive" ? `Received ${qty} ${product.unit}` : "Stocktake saved");
    });
  };

  return (
    <Drawer title={title} onClose={onClose}>
      <form className="form" onSubmit={submit}>
        <p className="muted num">{product.on_hand} {product.unit} on hand now</p>
        <ErrorNote error={error} />
        <Field
          label={action === "count" ? `How many did you count (${product.unit})` : `Quantity (${product.unit})`}
          hint={action === "count" && qty !== product.on_hand ? `That's ${qty > product.on_hand ? "+" : ""}${qty - product.on_hand} against the screen.` : undefined}
        >
          <input className="input num" type="number" required min={action === "count" ? 0 : 1} max={action === "use" ? product.on_hand : undefined}
                 value={qty} onChange={(e) => setQty(Number(e.target.value))} />
        </Field>
        {action === "use" && (
          <Field label="For client" hint="Optional. It will show in their history.">
            <select className="input" value={clientId} onChange={(e) => setClientId(e.target.value)}>
              <option value="">Not for a client</option>
              {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </Field>
        )}
        <Field label="Note" hint="Optional">
          <input className="input" maxLength={500} placeholder={action === "receive" ? "For example: Delivery from supplier" : ""} value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
        <div className="form-actions">
          <button type="button" className="btn btn-quiet" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" disabled={busy}>{action === "use" ? "Record use" : action === "receive" ? "Add to stock" : "Save count"}</button>
        </div>
      </form>
    </Drawer>
  );
}

function History({ product, clients, onClose }: { product: Product; clients: Client[]; onClose: () => void }) {
  const { data } = useLoad(async () => {
    const [moves, users] = await Promise.all([
      api<Movement[]>(`/api/inventory/movements?product_id=${product.id}`),
      api<User[]>("/api/users"),
    ]);
    return { moves, users };
  }, [product.id]);
  const who = (id: string) => data?.users.find((u) => u.id === id)?.name ?? "Someone";
  const client = (id: string | null) => clients.find((c) => c.id === id)?.name;

  return (
    <Drawer title={product.name} onClose={onClose}>
      <p className="muted" style={{ marginBottom: 12 }}>Every change to the stock level, newest first. The numbers always add up to what's on hand.</p>
      {data && data.moves.length ? (
        <ul className="list panel">
          {data.moves.map((m) => (
            <li key={m.id}>
              <span>
                <strong>{REASON[m.reason]}</strong>
                <span className="muted" style={{ display: "block", fontSize: "var(--fs-sm)" }}>
                  {new Date(m.created_at).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}, {who(m.created_by)}
                  {client(m.client_id) && `, for ${client(m.client_id)}`}
                </span>
                {m.note && <span style={{ display: "block", fontSize: "var(--fs-sm)" }}>{m.note}</span>}
              </span>
              <span className="num" style={{ textAlign: "right" }}>
                <strong style={{ color: m.change > 0 ? "var(--ok)" : "var(--danger)" }}>{m.change > 0 ? `+${m.change}` : m.change}</strong>
                <span className="muted" style={{ display: "block", fontSize: "var(--fs-xs)" }}>{m.balance_after} left</span>
              </span>
            </li>
          ))}
        </ul>
      ) : (
        data && <p className="muted">No changes recorded yet.</p>
      )}
    </Drawer>
  );
}
