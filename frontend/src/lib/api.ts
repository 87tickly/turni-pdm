/**
 * Client API per il backend COLAZIONE.
 * Gestisce autenticazione JWT e chiamate HTTP.
 */

const TOKEN_KEY = "colazione_token"

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
}

async function request<T>(
  url: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((options.headers as Record<string, string>) || {}),
  }
  if (token) {
    headers["Authorization"] = `Bearer ${token}`
  }

  const res = await fetch(url, { ...options, headers })

  if (res.status === 401) {
    clearToken()
    window.location.href = "/login"
    throw new Error("Non autenticato")
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Errore ${res.status}`)
  }

  return res.json()
}

export const api = {
  get: <T>(url: string) => request<T>(url),

  post: <T>(url: string, body?: unknown) =>
    request<T>(url, {
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
    }),

  delete: <T>(url: string) => request<T>(url, { method: "DELETE" }),
}

// ── Auth ──────────────────────────────────────────────────────────

export interface AuthResponse {
  token: string
  user: { id: number; username: string; is_admin: boolean }
}

export async function login(username: string, password: string) {
  const data = await api.post<AuthResponse>("/api/login", { username, password })
  setToken(data.token)
  return data
}

export async function register(username: string, password: string) {
  const data = await api.post<AuthResponse>("/api/register", { username, password })
  setToken(data.token)
  return data
}

export async function getMe() {
  return api.get<{ id: number; username: string; is_admin: boolean }>("/api/me")
}

// ── Health / Info ─────────────────────────────────────────────────

export interface DbInfo {
  total_segments: number
  material_turns: Array<{ id: number; turn_number: string }>
  day_indices: number[]
  unique_trains: string[]
  unique_trains_count: number
}

export async function getHealth() {
  return api.get<{ status: string; service: string }>("/api/health")
}

export async function getDbInfo() {
  return api.get<DbInfo>("/info")
}

// ── Constants ─────────────────────────────────────────────────────

export async function getConstants() {
  return api.get<Record<string, unknown>>("/constants")
}
