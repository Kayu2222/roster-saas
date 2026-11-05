import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import "./styles.css";
import { SessionProvider, useSession } from "./session";
import { ToastProvider } from "./components/ui";
import { Shell } from "./components/Shell";
import { Login, Register } from "./pages/Auth";
import { Today } from "./pages/Today";
import { Roster } from "./pages/Roster";
import { RosterSetup } from "./pages/RosterSetup";
import { People } from "./pages/People";
import { Resources } from "./pages/Resources";
import { Bookings } from "./pages/Bookings";
import { Settings } from "./pages/Settings";
import { Clients } from "./pages/Clients";
import { Stock } from "./pages/Stock";

function RequireSignIn({ children }: { children: ReactNode }) {
  const { me, loading } = useSession();
  if (loading) return null;
  return me ? <>{children}</> : <Navigate to="/login" replace />;
}

function GuestOnly({ children }: { children: ReactNode }) {
  const { me, loading } = useSession();
  if (loading) return null;
  return me ? <Navigate to="/" replace /> : <>{children}</>;
}

function ModuleRoute({ module, children }: { module: "roster" | "resource" | "inventory"; children: ReactNode }) {
  const { hasModule } = useSession();
  return hasModule(module) ? <>{children}</> : <Navigate to="/" replace />;
}

function App() {
  return (
    <Routes>
      <Route path="/login" element={<GuestOnly><Login /></GuestOnly>} />
      <Route path="/register" element={<GuestOnly><Register /></GuestOnly>} />
      <Route element={<RequireSignIn><Shell /></RequireSignIn>}>
        <Route index element={<Today />} />
        <Route path="roster" element={<ModuleRoute module="roster"><Roster /></ModuleRoute>} />
        <Route path="roster/setup" element={<ModuleRoute module="roster"><RosterSetup /></ModuleRoute>} />
        <Route path="bookings" element={<ModuleRoute module="resource"><Bookings /></ModuleRoute>} />
        <Route path="resources" element={<ModuleRoute module="resource"><Resources /></ModuleRoute>} />
        <Route path="stock" element={<ModuleRoute module="inventory"><Stock /></ModuleRoute>} />
        <Route path="clients" element={<Clients />} />
        <Route path="people" element={<People />} />
        <Route path="settings" element={<Settings />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <SessionProvider>
        <ToastProvider>
          <App />
        </ToastProvider>
      </SessionProvider>
    </BrowserRouter>
  </StrictMode>,
);
