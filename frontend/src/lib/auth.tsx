import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, type AuthStatus, type Role } from "@/lib/api";

interface AuthContextValue {
  status: AuthStatus | null;
  loading: boolean;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue>({ status: null, loading: true, refresh: async () => {} });

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [loading, setLoading] = useState(true);

  async function refresh() {
    try {
      const s = await api.authStatus();
      setStatus(s);
    } catch {
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  return <AuthContext.Provider value={{ status, loading, refresh }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}

/**
 * What the signed-in account may do, for deciding what to SHOW.
 *
 * Not for deciding what is allowed: that is settled in the backend
 * middleware, on every request, from the account row rather than from
 * anything the browser holds. Hiding a control the server would refuse is a
 * courtesy to the person using it -- a UI full of buttons that answer 403 is
 * a UI that lies about what your account is for.
 *
 * Both default to false while the status is still loading, so nothing
 * flashes into view and then disappears.
 */
export function usePermissions(): { role: Role | null; canWrite: boolean; isAdmin: boolean } {
  const { status } = useAuth();
  const role = status?.role ?? null;
  return {
    role,
    canWrite: role === "editor" || role === "admin",
    isAdmin: role === "admin",
  };
}
