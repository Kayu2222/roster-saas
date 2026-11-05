import { NavLink, Outlet } from "react-router-dom";
import { useSession } from "../session";
import { Icon } from "./ui";

export function Shell() {
  const { me, signOut, hasModule } = useSession();
  if (!me) return null;

  const links = [
    { to: "/", label: "Today", icon: "home", show: true },
    { to: "/roster", label: "Roster", icon: "calendar", show: hasModule("roster") },
    { to: "/bookings", label: "Bookings", icon: "clock", show: hasModule("resource") },
    { to: "/resources", label: "Resources", icon: "box", show: hasModule("resource") },
    { to: "/stock", label: "Stock", icon: "pill", show: hasModule("inventory") },
    { to: "/clients", label: "Clients", icon: "user", show: true },
    { to: "/people", label: "People", icon: "people", show: true },
    { to: "/settings", label: "Company", icon: "settings", show: true },
  ];

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true"><span /></div>
          <span className="brand-name">Roster</span>
        </div>
        <div className="company">
          <strong>{me.tenant.name}</strong>
          {me.user.role === "owner" ? "Owner" : me.user.role === "manager" ? "Manager" : "Staff"}
        </div>
        <nav className="nav" aria-label="Main">
          {links.filter((l) => l.show).map((l) => (
            <NavLink key={l.to} to={l.to} end={l.to === "/"}>
              <Icon name={l.icon} />
              {l.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          <div className="who">{me.user.name}</div>
          <button className="btn-link" onClick={signOut}>Sign out</button>
        </div>
      </aside>
      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}

export function PageHead({ title, sub, children }: { title: string; sub?: string; children?: React.ReactNode }) {
  return (
    <div className="page-head">
      <div>
        <h1 className="page-title">{title}</h1>
        {sub && <p className="page-sub">{sub}</p>}
      </div>
      {children && <div className="toolbar">{children}</div>}
    </div>
  );
}
