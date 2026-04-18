import { useEffect, useState } from "react"
import { Outlet, Navigate } from "react-router-dom"
import { Sidebar } from "./Sidebar"
import { CommandPalette } from "./CommandPalette"
import { useAuth } from "@/hooks/useAuth"

export function Layout() {
  const { user, loading, logout } = useAuth()
  const [paletteOpen, setPaletteOpen] = useState(false)

  // Hotkey globale ⌘K / Ctrl+K
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const isMeta = e.metaKey || e.ctrlKey
      if (isMeta && e.key.toLowerCase() === "k") {
        e.preventDefault()
        setPaletteOpen((o) => !o)
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen bg-background">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
          <p className="text-[13px] text-muted-foreground">Caricamento...</p>
        </div>
      </div>
    )
  }

  if (!user) {
    return <Navigate to="/login" replace />
  }

  return (
    <div className="flex min-h-screen bg-background">
      <Sidebar
        username={user.username}
        isAdmin={user.is_admin}
        onLogout={logout}
        onOpenPalette={() => setPaletteOpen(true)}
      />
      <main className="flex-1 ml-56">
        <div className="max-w-6xl mx-auto px-8 py-6">
          <Outlet />
        </div>
      </main>
      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        onLogout={logout}
      />
    </div>
  )
}
