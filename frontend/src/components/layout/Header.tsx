import { LogOut, User as UserIcon } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { useAuth } from "@/lib/auth/AuthContext";

export function Header() {
  const { user, logout } = useAuth();

  return (
    <header className="flex h-14 items-center justify-between border-b border-border bg-white px-6">
      <div className="text-sm text-muted-foreground">Pianificatore Giro Materiale</div>
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
