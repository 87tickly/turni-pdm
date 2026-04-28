import { Navigate, Outlet, useLocation } from "react-router-dom";

import { Spinner } from "@/components/ui/Spinner";
import { useAuth } from "@/lib/auth/AuthContext";

interface ProtectedRouteProps {
  /** Se fornito, l'utente deve avere questo ruolo (admin bypassa). */
  requiredRole?: string;
}

/**
 * Gating in 3 stati:
 * - loading: spinner full-screen mentre fetchamo /me
 * - unauthenticated: redirect a /login con state.from per ritorno post-login
 * - authenticated + role mismatch: redirect a /forbidden
 * - authenticated + role ok: <Outlet />
 */
export function ProtectedRoute({ requiredRole }: ProtectedRouteProps) {
  const { status, hasRole } = useAuth();
  const location = useLocation();

  if (status === "loading") {
    return (
      <div className="flex h-screen items-center justify-center">
        <Spinner label="Verifica sessione…" />
      </div>
    );
  }

  if (status === "unauthenticated") {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (requiredRole !== undefined && !hasRole(requiredRole)) {
    return <Navigate to="/forbidden" replace />;
  }

  return <Outlet />;
}
