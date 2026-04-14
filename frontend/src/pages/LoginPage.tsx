import { useState, type FormEvent } from "react"
import { useNavigate } from "react-router-dom"
import { login, register } from "@/lib/api"

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
    <div className="flex items-center justify-center min-h-screen bg-muted">
      <div className="w-full max-w-sm bg-card rounded-lg shadow-sm border border-border p-8">
        {/* Brand */}
        <div className="text-center mb-8">
          <h1 className="text-2xl font-semibold tracking-tight">COLAZIONE</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Gestionale Turni PDM
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1.5">Username</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full px-3 py-2 border border-input rounded-md text-sm bg-background focus:outline-none focus:ring-2 focus:ring-ring"
              placeholder="Il tuo username"
              required
              autoFocus
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1.5">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-3 py-2 border border-input rounded-md text-sm bg-background focus:outline-none focus:ring-2 focus:ring-ring"
              placeholder="La tua password"
              required
            />
          </div>

          {error && (
            <p className="text-sm text-destructive">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2 px-4 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-opacity"
          >
            {loading ? "..." : isRegister ? "Registrati" : "Accedi"}
          </button>
        </form>

        <div className="mt-4 text-center">
          <button
            onClick={() => {
              setIsRegister(!isRegister)
              setError("")
            }}
            className="text-sm text-muted-foreground hover:text-foreground transition-colors"
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
