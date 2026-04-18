import { useState, type FormEvent } from "react"
import { useNavigate } from "react-router-dom"
import { login, register } from "@/lib/api"
import { Logo } from "@/components/Logo"

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
    <div
      className="flex items-center justify-center min-h-screen relative overflow-hidden"
      style={{ backgroundColor: "var(--color-surface)" }}
    >
      {/* Subtle gradient orb */}
      <div
        className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[520px] h-[520px] rounded-full blur-3xl pointer-events-none"
        style={{ backgroundColor: "rgba(0, 98, 204, 0.05)" }}
      />
      <div
        className="absolute bottom-[-120px] right-[-120px] w-[320px] h-[320px] rounded-full blur-3xl pointer-events-none"
        style={{ backgroundColor: "rgba(34, 197, 94, 0.06)" }}
      />

      <div className="relative w-full max-w-sm px-4">
        {/* Brand */}
        <div className="flex flex-col items-center mb-8">
          <Logo size="lg" />
          <div
            className="text-[10px] font-bold uppercase mt-3"
            style={{
              color: "var(--color-on-surface-quiet)",
              letterSpacing: "0.12em",
            }}
          >
            Gestionale Turni PdC
          </div>
          <p
            className="text-[13px] mt-1"
            style={{ color: "var(--color-on-surface-muted)" }}
          >
            Personale di macchina
          </p>
        </div>

        {/* Card */}
        <div
          className="rounded-2xl p-6"
          style={{
            backgroundColor: "var(--color-surface-container-lowest)",
            boxShadow: "var(--shadow-lg)",
          }}
        >
          <div
            className="text-[10px] font-bold uppercase mb-3"
            style={{
              color: "var(--color-on-surface-quiet)",
              letterSpacing: "0.12em",
            }}
          >
            {isRegister ? "Registrazione" : "Accesso"}
          </div>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label
                className="block text-[12px] font-semibold mb-1.5"
                style={{ color: "var(--color-on-surface-muted)" }}
              >
                Username
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full px-3 py-2.5 rounded-lg text-[13px] outline-none transition-all focus:ring-2"
                style={{
                  backgroundColor: "var(--color-surface-container-low)",
                  color: "var(--color-on-surface-strong)",
                  boxShadow: "inset 0 0 0 1px var(--color-ghost)",
                  fontFamily: "var(--font-sans)",
                }}
                placeholder="Il tuo username"
                required
                autoFocus
              />
            </div>

            <div>
              <label
                className="block text-[12px] font-semibold mb-1.5"
                style={{ color: "var(--color-on-surface-muted)" }}
              >
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-3 py-2.5 rounded-lg text-[13px] outline-none transition-all focus:ring-2"
                style={{
                  backgroundColor: "var(--color-surface-container-low)",
                  color: "var(--color-on-surface-strong)",
                  boxShadow: "inset 0 0 0 1px var(--color-ghost)",
                  fontFamily: "var(--font-sans)",
                }}
                placeholder="La tua password"
                required
              />
            </div>

            {error && (
              <div
                className="text-[12px] p-2.5 rounded-lg"
                style={{
                  backgroundColor: "var(--color-destructive-container)",
                  color: "var(--color-destructive)",
                }}
              >
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 px-4 rounded-lg text-[13.5px] font-semibold text-white transition-opacity disabled:opacity-50 hover:opacity-90"
              style={{
                background: "var(--gradient-primary)",
                boxShadow: "var(--shadow-md)",
              }}
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
        <div className="mt-5 text-center">
          <button
            onClick={() => {
              setIsRegister(!isRegister)
              setError("")
            }}
            className="text-[12px] transition-colors"
            style={{ color: "var(--color-on-surface-muted)" }}
            onMouseEnter={(e) =>
              (e.currentTarget.style.color = "var(--color-on-surface-strong)")
            }
            onMouseLeave={(e) =>
              (e.currentTarget.style.color = "var(--color-on-surface-muted)")
            }
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
