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

// ── Treni (DB locale) ────────────────────────────────────────────

export interface TrainSegment {
  train_id: string
  from_station: string
  to_station: string
  dep_time: string
  arr_time: string
  is_deadhead?: boolean
  material_turn_id?: number
  day_index?: number
}

export interface TrainQueryResult {
  train_id: string
  segments: TrainSegment[]
}

export async function queryTrain(trainId: string) {
  return api.get<TrainQueryResult>(`/train/${trainId}`)
}

export interface StationResult {
  station: string
  departures: TrainSegment[]
  arrivals: TrainSegment[]
}

export async function queryStation(stationName: string) {
  return api.get<StationResult>(`/station/${encodeURIComponent(stationName)}`)
}

export async function listStations() {
  return api.get<{ stations: string[]; count: number }>("/stations")
}

// ── Giro materiale ───────────────────────────────────────────────

export interface GiroChainContext {
  train_id: string
  turn_number: string | null
  position: number
  total: number
  chain: Array<{
    train_id: string
    from: string
    to: string
    dep: string
    arr: string
    is_deadhead?: boolean
  }>
  prev: Record<string, string> | null
  next: Record<string, string> | null
}

export async function getGiroChain(trainId: string) {
  return api.get<GiroChainContext>(`/giro-chain/${trainId}`)
}

// ── VT / ARTURO Live ─────────────────────────────────────────────

export interface VtStation {
  name: string
  code: string
}

export async function vtAutocompleteStation(q: string) {
  return api.get<{ stations: VtStation[] }>(`/vt/autocomplete-station?q=${encodeURIComponent(q)}`)
}

export interface VtDeparture {
  train_number: string | number
  category: string
  destination: string
  dep_time: string
  delay: number
  platform_scheduled: string | null
  platform_actual: string | null
  running: boolean
  operator: string
}

export async function vtDepartures(stationCode: string, onlyTrenord = false) {
  return api.get<{ station_code: string; departures: VtDeparture[]; count: number }>(
    `/vt/departures?station_code=${stationCode}&only_trenord=${onlyTrenord}`
  )
}

export async function vtArrivals(stationCode: string, onlyTrenord = false) {
  return api.get<{ station_code: string; arrivals: VtDeparture[]; count: number }>(
    `/vt/arrivals?station_code=${stationCode}&only_trenord=${onlyTrenord}`
  )
}

export interface VtStop {
  station: string
  station_code: string
  scheduled_dep: string | null
  scheduled_arr: string | null
  actual_dep: string | null
  actual_arr: string | null
  delay_dep: number
  delay_arr: number
  platform_scheduled: string | null
  platform_actual: string | null
  stop_type: string
  cancelled: boolean
}

export interface VtTrainInfo {
  train_number: number
  origin_code: string
  operator: string
  is_trenord: boolean
  status: string
  last_update: string | null
  delay: number
  stops: VtStop[]
  cancelled_stops: string[]
}

export async function vtTrainInfo(trainNumber: number) {
  return api.get<VtTrainInfo>(`/vt/train-info?train_number=${trainNumber}`)
}
