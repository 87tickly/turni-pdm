import { Outlet } from "react-router-dom";

import { Header } from "@/components/layout/Header";
import { Sidebar } from "@/components/layout/Sidebar";
import { SidebarProvider } from "@/components/layout/SidebarContext";

/**
 * Shell autenticata: sidebar + header + main content per `<Outlet />`.
 *
 * Sprint 7.11 MR 7.11.5: il `SidebarProvider` introduce lo stato
 * collapsed/expanded condiviso tra Sidebar e Header (toggle nel topbar).
 * Persistente in localStorage chiave `arturo:sidebar:collapsed`.
 */
export function AppLayout() {
  return (
    <SidebarProvider>
      <div className="flex h-screen overflow-hidden text-foreground">
        <Sidebar />
        {/* Sprint 7.10 MR α.8.fix: `min-w-0` sul colonna right + sul
            main blocca la propagazione del width dei figli (es. Gantt
            a zoom 200% con innerWidth 2140px) attraverso tutto il
            flex-col chain. Senza, il content largo espande Card →
            toolbar → spinge la sezione destra fuori dal viewport. */}
        <div className="flex min-w-0 flex-1 flex-col">
          <Header />
          <main className="min-w-0 flex-1 overflow-auto p-6">
            <Outlet />
          </main>
        </div>
      </div>
    </SidebarProvider>
  );
}
