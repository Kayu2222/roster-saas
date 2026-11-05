import { useState, type FormEvent, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type Module } from "../api";
import { useSession } from "../session";
import { ErrorNote, Field, useSubmit } from "../components/ui";

function AuthLayout({ children }: { children: ReactNode }) {
  // A tiny week of magnets: the product's core idea, shown before any words about it.
  const week = [
    { d: "Mon", m: ["#2a9d8f", "#4c5fd5"] },
    { d: "Tue", m: ["#e0694b", "#2a9d8f", "#d99a2b"] },
    { d: "Wed", m: ["#4c5fd5"] },
    { d: "Thu", m: ["#2a9d8f", "#9156d6"] },
    { d: "Fri", m: ["#e0694b", "#4c5fd5", "#2a9d8f"] },
  ];
  return (
    <div className="auth">
      <section className="auth-side">
        <div>
          <h1>Who works when, and who has the room.</h1>
          <p>Plan rosters and book rooms, beds or vehicles for your team, in one place.</p>
        </div>
        <div className="mini-board" aria-hidden="true">
          {week.map((col) => (
            <div className="col" key={col.d}>
              <span>{col.d}</span>
              {col.m.map((c, i) => <span key={i} className="m" style={{ ["--m" as string]: c }} />)}
            </div>
          ))}
        </div>
      </section>
      <section className="auth-main">{children}</section>
    </div>
  );
}

export function Login() {
  const { signIn } = useSession();
  const navigate = useNavigate();
  const { busy, error, run } = useSubmit();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const submit = (e: FormEvent) => {
    e.preventDefault();
    run(async () => {
      const { access_token } = await api<{ access_token: string }>("/api/auth/login", {
        method: "POST",
        body: { email, password },
      });
      await signIn(access_token);
      navigate("/");
    });
  };

  return (
    <AuthLayout>
      <form className="auth-card form" onSubmit={submit}>
        <h2>Sign in</h2>
        <ErrorNote error={error} />
        <Field label="Email">
          <input className="input" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Field label="Password">
          <input className="input" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <button className="btn btn-primary" disabled={busy}>{busy ? "Signing in" : "Sign in"}</button>
        <p className="muted">New here? <Link to="/register">Set up your company</Link></p>
      </form>
    </AuthLayout>
  );
}

export function Register() {
  const { signIn } = useSession();
  const navigate = useNavigate();
  const { busy, error, setError, run } = useSubmit();
  const [form, setForm] = useState({ company_name: "", owner_name: "", email: "", password: "" });
  const [modules, setModules] = useState<Module[]>(["roster"]);

  const toggle = (m: Module) =>
    setModules((cur) => (cur.includes(m) ? cur.filter((x) => x !== m) : [...cur, m]));

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!modules.length) return setError("Choose at least one: rosters, bookings, or both.");
    run(async () => {
      const { access_token } = await api<{ access_token: string }>("/api/auth/register", {
        method: "POST",
        body: { ...form, modules },
      });
      await signIn(access_token);
      navigate("/");
    });
  };

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [k]: e.target.value });

  return (
    <AuthLayout>
      <form className="auth-card form" onSubmit={submit}>
        <h2>Set up your company</h2>
        <ErrorNote error={error} />
        <Field label="Company name">
          <input className="input" required minLength={2} value={form.company_name} onChange={set("company_name")} />
        </Field>
        <Field label="Your name">
          <input className="input" required autoComplete="name" value={form.owner_name} onChange={set("owner_name")} />
        </Field>
        <Field label="Work email">
          <input className="input" type="email" required autoComplete="email" value={form.email} onChange={set("email")} />
        </Field>
        <Field label="Password" hint="At least 8 characters">
          <input className="input" type="password" required minLength={8} maxLength={64} autoComplete="new-password" value={form.password} onChange={set("password")} />
        </Field>
        <fieldset className="module-choice" style={{ border: 0, padding: 0, margin: 0 }}>
          <legend className="field" style={{ marginBottom: 8 }}><span>What do you need?</span></legend>
          <label>
            <input type="checkbox" checked={modules.includes("roster")} onChange={() => toggle("roster")} />
            <strong>Staff rosters</strong>
            <small>Job roles, shift templates and a weekly roster.</small>
          </label>
          <label>
            <input type="checkbox" checked={modules.includes("resource")} onChange={() => toggle("resource")} />
            <strong>Resource bookings</strong>
            <small>Rooms, beds, vehicles or equipment people can book.</small>
          </label>
        </fieldset>
        <button className="btn btn-primary" disabled={busy}>{busy ? "Creating company" : "Create company"}</button>
        <p className="muted">Already set up? <Link to="/login">Sign in</Link></p>
      </form>
    </AuthLayout>
  );
}
