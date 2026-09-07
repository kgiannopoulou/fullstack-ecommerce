"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { apiFetch } from "./api";

export type AuthUser = {
  id: number;
  email: string;
  role: "user" | "admin";
};

type AuthContextValue = {
  user: AuthUser | null;
  loading: boolean;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

// Wraps the whole app (see layout.tsx) so any component can call useAuth()
// to find out who's signed in. The actual session lives in an httpOnly
// cookie the frontend can't read directly — this context's job is just to
// ask the backend "who am I?" via GET /api/auth/me and cache the answer.
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  // True until the initial /api/auth/me call resolves. Consumers (e.g. the
  // cart page's checkout button) use this to avoid flashing a "logged out"
  // state before the real session status is known.
  const [loading, setLoading] = useState(true);

  async function refresh() {
    try {
      const data = await apiFetch<{ user: AuthUser | null }>("/api/auth/me");
      setUser(data.user);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }

  async function logout() {
    await apiFetch("/api/auth/logout", { method: "POST" });
    setUser(null);
  }

  // Check session status once when the app first loads.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial session fetch on mount
    refresh();
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, refresh, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
