import { Outlet, Navigate } from "react-router-dom"
import { Sidebar } from "./Sidebar"
import { useAuth } from "@/hooks/useAuth"

export function Layout() {
  const { user, loading, logout } = useAuth()

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-muted-foreground text-sm">Caricamento...</div>
      </div>
    )
  }

  if (!user) {
    return <Navigate to="/login" replace />
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar
        username={user.username}
        isAdmin={user.is_admin}
        onLogout={logout}
      />
      <main className="flex-1 ml-60 p-8">
        <Outlet />
      </main>
    </div>
  )
}
