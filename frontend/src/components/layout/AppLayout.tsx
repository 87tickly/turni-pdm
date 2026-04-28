import { Outlet } from "react-router-dom";

import { Header } from "@/components/layout/Header";
import { Sidebar } from "@/components/layout/Sidebar";

/** Shell autenticata: sidebar + header + main content per `<Outlet />`. */
export function AppLayout() {
  return (
    <div className="flex h-screen overflow-hidden text-foreground">
      <Sidebar />
      <div className="flex flex-1 flex-col">
        <Header />
        <main className="flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
