import { LogOut, User as UserIcon } from "lucide-react";
import { useLocation } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { useAuth } from "@/lib/auth/AuthContext";

/** Mappa path → titolo header, valutato dal primo segmento di location. */
function titleForPath(pathname: string): string {
  if (pathname.startsWith("/pianificatore-pdc")) return "Pianificatore Turno PdC";
  if (pathname.startsWith("/pianificatore-giro")) return "Pianificatore Giro Materiale";
  return "Colazione";
}

export function Header() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const title = titleForPath(location.pathname);

  return (
    <header className="flex h-14 items-center justify-between border-b border-border bg-white px-6">
      <div className="text-sm font-medium tracking-wide text-primary/80">{title}</div>
      <div className="flex items-center gap-3">
        {user !== null && (
          <span className="flex items-center gap-2 text-sm">
            <UserIcon className="h-4 w-4 text-muted-foreground" aria-hidden />
            <span className="font-medium">{user.username}</span>
            {user.is_admin && (
              <span className="rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-primary">
                admin
              </span>
            )}
            <span className="text-xs text-muted-foreground">azienda #{user.azienda_id}</span>
          </span>
        )}
        <Button variant="ghost" size="sm" onClick={logout} aria-label="Esci">
          <LogOut className="mr-2 h-4 w-4" aria-hidden />
          Esci
        </Button>
      </div>
    </header>
  );
}
