/**
 * AuthContext — stato autenticazione globale.
 *
 * Bootstrap: al mount, se ci sono token in storage, prova /api/auth/me.
 * Se OK → user popolato; se KO → token cancellati, user = null.
 *
 * Login: scambia username+password → token, poi GET /me per popolare user.
 * Logout: cancella token, user = null. Il router redirige a /login.
 *
 * Hook fallimento refresh: registriamo `setOnAuthInvalid` che azzera
 * lo state in memoria (i token sono già stati cancellati dal client).
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { ReactNode } from "react";

import { ApiError, setOnAuthInvalid } from "@/lib/api/client";
import { fetchCurrentUser, loginApi } from "@/lib/api/auth";
import type { CurrentUser } from "@/lib/api/auth";
import {
  clearTokens,
  getAccessToken,
  setAccessToken,
  setRefreshToken,
} from "@/lib/auth/tokenStorage";

export type AuthStatus = "loading" | "authenticated" | "unauthenticated";

interface AuthContextValue {
  status: AuthStatus;
  user: CurrentUser | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  hasRole: (role: string) => boolean;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<CurrentUser | null>(null);
  const isMountedRef = useRef(true);

  const logout = useCallback(() => {
    clearTokens();
    setUser(null);
    setStatus("unauthenticated");
  }, []);

  // Registra il callback per quando il refresh fallisce nel client.
  // I token sono già cancellati dal client: qui sincronizziamo lo state React.
  useEffect(() => {
    setOnAuthInvalid(() => {
      if (!isMountedRef.current) return;
      setUser(null);
      setStatus("unauthenticated");
    });
    return () => {
      setOnAuthInvalid(() => {});
    };
  }, []);

  // Bootstrap: con token presente prova a recuperare l'utente corrente.
  useEffect(() => {
    isMountedRef.current = true;
    const access = getAccessToken();
    if (access === null) {
      setStatus("unauthenticated");
      return () => {
        isMountedRef.current = false;
      };
    }
    let cancelled = false;
    void (async () => {
      try {
        const me = await fetchCurrentUser();
        if (cancelled) return;
        setUser(me);
        setStatus("authenticated");
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 401) {
          // client ha già tentato refresh; comunque pulizia esplicita
          clearTokens();
        }
        setUser(null);
        setStatus("unauthenticated");
      }
    })();
    return () => {
      cancelled = true;
      isMountedRef.current = false;
    };
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const tokens = await loginApi({ username, password });
    setAccessToken(tokens.access_token);
    setRefreshToken(tokens.refresh_token);
    const me = await fetchCurrentUser();
    setUser(me);
    setStatus("authenticated");
  }, []);

  const hasRole = useCallback(
    (role: string) => {
      if (user === null) return false;
      return user.is_admin || user.roles.includes(role);
    },
    [user],
  );

  const value = useMemo<AuthContextValue>(
    () => ({ status, user, login, logout, hasRole }),
    [status, user, login, logout, hasRole],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (ctx === null) {
    throw new Error("useAuth deve essere usato dentro <AuthProvider>");
  }
  return ctx;
}
