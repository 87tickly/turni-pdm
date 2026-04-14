import { useState, type FormEvent } from "react"
import { useNavigate } from "react-router-dom"
import { login, register } from "@/lib/api"
import { Train } from "lucide-react"

export function LoginPage() {
  const navigate = useNavigate()
  const [isRegister, setIsRegister] = useState(false)
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError("")
    setLoading(true)

    try {
      if (isRegister) {
        await register(username, password)
      } else {
        await login(username, password)
      }
      navigate("/", { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : "Errore di autenticazione")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex items-center justify-center min-h-screen bg-background">
      {/* Glow effect */}
      <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 h-96 bg-primary/5 rounded-full blur-3xl pointer-events-none" />

      <div className="relative w-full max-w-sm">
        {/* Brand */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-primary/10 border border-primary/20 mb-4">
            <Train size={22} className="text-primary" />
          </div>
          <h1 className="text-xl font-semibold tracking-tight">COLAZIONE</h1>
          <p className="text-[13px] text-muted-foreground mt-1">
            Gestionale Turni PDM
          </p>
        </div>

        {/* Card */}
        <div className="bg-card rounded-xl border border-border-subtle p-6">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-[12px] font-medium text-muted-foreground mb-1.5">
                Username
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full px-3 py-2 bg-muted border border-border rounded-lg text-[13px] text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary transition-colors"
                placeholder="Il tuo username"
                required
                autoFocus
              />
            </div>

            <div>
              <label className="block text-[12px] font-medium text-muted-foreground mb-1.5">
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-3 py-2 bg-muted border border-border rounded-lg text-[13px] text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary transition-colors"
                placeholder="La tua password"
                required
              />
            </div>

            {error && (
              <div className="bg-destructive/10 text-destructive text-[12px] p-2.5 rounded-lg border border-destructive/20">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2 px-4 bg-primary text-primary-foreground rounded-lg text-[13px] font-medium hover:bg-primary-hover disabled:opacity-50 transition-colors"
            >
              {loading ? (
                <span className="inline-flex items-center gap-2">
                  <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  ...
                </span>
              ) : isRegister ? (
                "Crea account"
              ) : (
                "Accedi"
              )}
            </button>
          </form>
        </div>

        {/* Toggle */}
        <div className="mt-4 text-center">
          <button
            onClick={() => {
              setIsRegister(!isRegister)
              setError("")
            }}
            className="text-[12px] text-muted-foreground hover:text-foreground transition-colors"
          >
            {isRegister
              ? "Hai gia un account? Accedi"
              : "Non hai un account? Registrati"}
          </button>
        </div>
      </div>
    </div>
  )
}
