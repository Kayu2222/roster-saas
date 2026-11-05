import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, getToken, setToken, type Me, type Module } from "./api";

interface Session {
  me: Me | null;
  loading: boolean;
  signIn: (token: string) => Promise<void>;
  signOut: () => void;
  refresh: () => Promise<void>;
  hasModule: (m: Module) => boolean;
  canManage: boolean;
}

const SessionContext = createContext<Session | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    if (!getToken()) {
      setMe(null);
      setLoading(false);
      return;
    }
    try {
      setMe(await api<Me>("/api/me"));
    } catch {
      setMe(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const onSignedOut = () => setMe(null);
    window.addEventListener("roster:signed-out", onSignedOut);
    return () => window.removeEventListener("roster:signed-out", onSignedOut);
  }, [refresh]);

  const signIn = async (token: string) => {
    setToken(token);
    setLoading(true);
    await refresh();
  };

  const signOut = () => {
    setToken(null);
    setMe(null);
  };

  const value: Session = {
    me,
    loading,
    signIn,
    signOut,
    refresh,
    hasModule: (m) => !!me?.tenant.modules.includes(m),
    canManage: me?.user.role === "owner" || me?.user.role === "manager",
  };
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): Session {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used inside SessionProvider");
  return ctx;
}
