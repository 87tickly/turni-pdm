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
        <div className="flex flex-1 flex-col">
          <Header />
          <main className="flex-1 overflow-auto p-6">
            <Outlet />
          </main>
        </div>
      </div>
    </SidebarProvider>
  );
}
