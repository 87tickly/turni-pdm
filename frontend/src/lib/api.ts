/**
 * Client API per il backend COLAZIONE.
 * Gestisce autenticazione JWT e chiamate HTTP.
 *
 * In Tauri (desktop): le fetch vanno a http://localhost:8002
 * In browser (dev/prod): le fetch vanno a path relativi (proxy Vite o stesso server)
 */

// Rileva se siamo in Tauri (desktop app)
const IS_TAURI = typeof window !== "undefined" && "__TAURI__" in window
const API_BASE = IS_TAURI ? "http://localhost:8002" : ""

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

  const fullUrl = url.startsWith("http") ? url : `${API_BASE}${url}`
  const res = await fetch(fullUrl, { ...options, headers })

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

  put: <T>(url: string, body?: unknown) =>
    request<T>(url, {
      method: "PUT",
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
  material_turns: Array<{
    id: number
    turn_number: string
    material_type?: string
  }>
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

export interface AppConstants {
  MAX_PRESTAZIONE_MIN: number
  MAX_CONDOTTA_MIN: number
  TARGET_CONDOTTA_MIN: number
  MEAL_MIN: number
  EXTRA_START_MIN: number
  EXTRA_END_MIN: number
  ACCESSORY_OPTIONS: Record<string, { label: string; start: number; end: number }>
  DEPOSITI: string[]
  FR_STATIONS: string[]
  [key: string]: unknown
}

export async function getConstants() {
  return api.get<AppConstants>("/constants")
}

// ── Validazione giornata ─────────────────────────────────────────

export interface Violation {
  rule: string
  message: string
  severity: string
}

export interface ValidateDayResult {
  prestazione_min: number
  prestazione: string
  limite_prestazione: string
  condotta_min: number
  condotta: string
  limite_condotta: string
  meal_min: number
  accessori_min: number
  tempi_medi_min: number
  extra_min: number
  night_minutes: number
  day_type: string
  presentation_time: string
  end_time: string
  is_fr: boolean
  last_station: string
  meal_start: string | null
  meal_end: string | null
  segments: TrainSegment[]
  timeline: TimelineBlock[]
  violations: Violation[]
  valid: boolean
}

export async function validateDayWithTimeline(params: {
  train_ids: string[]
  deposito: string
  accessory_type?: string
  deadhead_ids?: string[]
  is_fr?: boolean
}) {
  return api.post<ValidateDayResult>("/validate-day-with-timeline", {
    ...params,
    include_timeline: true,
  })
}

// ── Connections (treni in partenza da stazione) ──────────────────

export interface Connection {
  train_id: string
  from_station: string
  to_station: string
  dep_time: string
  arr_time: string
  giro_next: string | null
  giro_turn: string | null
}

export async function getConnections(params: {
  from_station: string
  after_time?: string
  to_station?: string
  day_type?: string
  exclude?: string
}) {
  const qs = new URLSearchParams()
  qs.set("from_station", params.from_station)
  if (params.after_time) qs.set("after_time", params.after_time)
  if (params.to_station) qs.set("to_station", params.to_station)
  if (params.day_type) qs.set("day_type", params.day_type)
  if (params.exclude) qs.set("exclude", params.exclude)
  return api.get<{ connections: Connection[]; count: number }>(`/connections?${qs}`)
}

// ── Salvataggio turno ────────────────────────────────────────────

export async function saveShift(params: {
  name: string
  deposito: string
  day_type: string
  train_ids: string[]
  deadhead_ids?: string[]
  prestazione_min: number
  condotta_min: number
  meal_min: number
  accessori_min: number
  extra_min: number
  is_fr: boolean
  last_station: string
  violations: Violation[]
  accessory_type: string
  presentation_time: string
  end_time: string
}) {
  return api.post<{ id: number; status: string }>("/save-shift", params)
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
  material_type?: string
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

// ── Turni salvati ────────────────────────────────────────────────

export interface SavedShift {
  id: number
  name: string
  deposito: string
  day_type: string
  created_at: string
  train_ids: string[] | string
  deadhead_ids: string[] | string
  prestazione_min: number
  condotta_min: number
  meal_min: number
  accessori_min: number
  extra_min: number
  is_fr: number | boolean
  last_station: string
  violations: string | Array<{ rule: string; message: string; severity: string }>
  accessory_type: string
  presentation_time: string
  end_time: string
  user_id: number
}

export async function getSavedShifts(dayType?: string) {
  const params = dayType ? `?day_type=${dayType}` : ""
  return api.get<{ shifts: SavedShift[]; count: number }>(`/saved-shifts${params}`)
}

export async function deleteSavedShift(shiftId: number) {
  return api.delete<{ status: string }>(`/saved-shift/${shiftId}`)
}

export interface TimelineBlock {
  type: string
  label: string
  detail?: string
  train_id?: string
  start: number
  end: number
  start_time: string
  end_time: string
  duration: number
  from_station: string
  to_station: string
  is_deadhead?: boolean
}

export interface ShiftTimeline {
  shift_id: number
  name: string
  deposito: string
  prestazione_min: number
  condotta_min: number
  meal_min: number
  accessori_min: number
  extra_min: number
  presentation_time: string
  end_time: string
  is_fr: boolean
  last_station: string
  timeline: TimelineBlock[]
  segments: TrainSegment[]
  violations: Array<{ rule: string; message: string; severity: string }>
}

export async function getShiftTimeline(shiftId: number) {
  return api.get<ShiftTimeline>(`/saved-shift/${shiftId}/timeline`)
}

// ── Turni settimanali ────────────────────────────────────────────

export interface DayVariant {
  id: number
  weekly_shift_id: number
  day_number: number
  variant_type: string
  day_type: string
  train_ids: string[]
  prestazione_min: number
  condotta_min: number
  meal_min: number
  is_fr: boolean
  is_scomp: boolean
  scomp_duration_min: number
  last_station: string
  violations: Array<{ rule: string; message: string }>
}

export interface WeeklyDay {
  day_number: number
  variants: DayVariant[]
}

export interface WeeklyShift {
  id: number
  name: string
  deposito: string
  created_at: string
  num_days: number
  weekly_prestazione_min: number
  weekly_condotta_min: number
  weighted_hours_per_day: number
  accessory_type: string
  notes: string
  user_id: number
  days?: WeeklyDay[]
}

export async function getWeeklyShifts() {
  return api.get<{ shifts: WeeklyShift[] }>("/weekly-shifts")
}

export async function deleteWeeklyShift(weeklyId: number) {
  return api.delete<{ message: string }>(`/weekly-shift/${weeklyId}`)
}

// ── Import / Upload PDF ─────────────────────────────────────────

export interface UploadResult {
  filename: string
  segments_imported: number
  total_segments_db: number
  unique_trains: string[]
  unique_trains_count: number
  turn_numbers: string[]
  confidence: { high: number; medium: number; low: number }
  warnings: string[]
  previous_data_cleared: boolean
  previous_segments_cleared: number
  saved_shift_warnings: string[]
}

export interface TurnoPersonaleResult {
  source_file: string
  pages_parsed: number
  days: Array<Record<string, unknown>>
  parse_warning?: string
}

export interface PdcTurnSummary {
  codice: string
  impianto: string
  planning: string
  days: number
  notes: number
  valid_from: string
  valid_to: string
}

export interface PdcImportDiff {
  new: Array<{ codice: string; impianto: string }>
  updated: Array<{ codice: string; impianto: string }>
  only_in_old: Array<{ codice: string; impianto: string }>
  counts: { new: number; updated: number; only_in_old: number }
}

// Risposta dry_run: preview senza scrivere nel DB
export interface TurnoPdcPreviewResult {
  status: "preview"
  filename: string
  n_pagine_pdf: number
  turni_parsed: number
  diff: PdcImportDiff
  summary: PdcTurnSummary[]
}

export interface TurnoPdcResult {
  status: string
  filename: string
  turni_imported: number
  turni_superseded?: number    // versioning (schema v2.1)
  import_id?: number           // versioning
  days_imported: number
  blocks_imported: number
  notes_imported: number
  trains_cited?: number
  stats: PdcStats
  summary: PdcTurnSummary[]
  diff?: PdcImportDiff          // versioning: stesso diff del preview
}

export interface PdcImportRecord {
  id: number
  filename: string
  data_stampa: string
  data_pubblicazione: string
  valido_dal: string
  valido_al: string
  n_turni: number
  n_pagine_pdf: number
  imported_at: string
  imported_by: number | null
  turni_attivi: number
}

export interface PdcStats {
  loaded: boolean
  turni: number
  days: number
  blocks: number
  trains: number
  impianti: string[]
  valid_from?: string
  valid_to?: string
  imported_at?: string
}

export interface PdcTurn {
  id: number
  codice: string
  planning: string
  impianto: string
  profilo: string
  valid_from: string
  valid_to: string
  source_file: string
  imported_at: string
}

export interface PdcBlock {
  id: number
  pdc_turn_day_id: number
  seq: number
  block_type: "train" | "coach_transfer" | "cv_partenza" | "cv_arrivo" | "meal" | "scomp" | "available"
  train_id: string
  vettura_id: string
  from_station: string
  to_station: string
  start_time: string
  end_time: string
  accessori_maggiorati: number
  // Schema v2.1 (MDL-PdC v1.0) — popolati dal parser v2, legacy vuoti
  minuti_accessori?: string  // es. "5", "27", "10" — riga ausiliaria PDF
  fonte_orario?: "parsed" | "interpolated" | "user"
  cv_parent_block_id?: number | null
  accessori_note?: string
}

export interface PdcDay {
  id: number
  pdc_turn_id: number
  day_number: number
  periodicita: string
  start_time: string
  end_time: string
  lavoro_min: number
  condotta_min: number
  km: number
  notturno: number
  riposo_min: number
  is_disponibile: number
  blocks: PdcBlock[]
}

export interface PdcNote {
  id: number
  train_id: string
  periodicita_text: string
  non_circola_dates: string[]
  circola_extra_dates: string[]
}

export interface PdcTurnDetail {
  turn: PdcTurn
  days: PdcDay[]
  notes: PdcNote[]
}

async function uploadFile<T>(url: string, file: File): Promise<T> {
  const token = getToken()
  const formData = new FormData()
  formData.append("file", file)

  const fullUrl = url.startsWith("http") ? url : `${API_BASE}${url}`
  const headers: Record<string, string> = {}
  if (token) {
    headers["Authorization"] = `Bearer ${token}`
  }
  // Non impostare Content-Type — il browser lo imposta con il boundary

  const res = await fetch(fullUrl, {
    method: "POST",
    headers,
    body: formData,
  })

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

export async function uploadTurnoMateriale(file: File) {
  return uploadFile<UploadResult>("/upload", file)
}

export async function uploadTurnoPersonale(file: File) {
  return uploadFile<TurnoPersonaleResult>("/upload-turno-personale", file)
}

export async function uploadTurnoPdc(file: File) {
  return uploadFile<TurnoPdcResult>("/upload-turno-pdc", file)
}

/** Preview (dry_run) del caricamento PDF PdC: calcola il diff con i
 *  turni attivi nel DB senza scrivere nulla. */
export async function uploadTurnoPdcPreview(file: File) {
  return uploadFile<TurnoPdcPreviewResult>("/upload-turno-pdc?dry_run=true", file)
}

export async function listPdcImports() {
  return api.get<{ count: number; imports: PdcImportRecord[] }>("/pdc-imports")
}

export async function getPdcStats() {
  return api.get<PdcStats>("/pdc-stats")
}

export async function listPdcTurns(params?: { impianto?: string; profilo?: string }) {
  const query = new URLSearchParams()
  if (params?.impianto) query.append("impianto", params.impianto)
  if (params?.profilo) query.append("profilo", params.profilo)
  const qs = query.toString()
  return api.get<{ count: number; turns: PdcTurn[] }>(
    `/pdc-turns${qs ? "?" + qs : ""}`
  )
}

export async function getPdcTurn(turnId: number) {
  return api.get<PdcTurnDetail>(`/pdc-turn/${turnId}`)
}

// ── PdC Builder: creazione / modifica / eliminazione turni manuali ──

export interface PdcBlockInput {
  seq?: number
  block_type: "train" | "coach_transfer" | "cv_partenza" | "cv_arrivo" | "meal" | "scomp" | "available"
  train_id?: string
  vettura_id?: string
  from_station?: string
  to_station?: string
  start_time?: string
  end_time?: string
  accessori_maggiorati?: boolean
  // Schema v2.1: minuti accessori (riga ausiliaria PDF). Per i treni il
  // formato consigliato e' "5/10" (5 min prep inizio + 10 min consegna fine)
  // o un singolo numero per refezione/cv (durata o offset).
  minuti_accessori?: string
}

export interface PdcDayInput {
  day_number: number
  periodicita: string
  start_time?: string
  end_time?: string
  lavoro_min?: number
  condotta_min?: number
  km?: number
  notturno?: boolean
  riposo_min?: number
  is_disponibile?: boolean
  blocks?: PdcBlockInput[]
}

export interface PdcTurnInput {
  codice: string
  planning?: string
  impianto: string
  profilo?: "Condotta" | "Scorta"
  valid_from?: string
  valid_to?: string
  days?: PdcDayInput[]
  notes?: Array<{
    train_id: string
    periodicita_text?: string
    non_circola_dates?: string[]
    circola_extra_dates?: string[]
  }>
}

export async function createPdcTurn(data: PdcTurnInput) {
  return api.post<{
    status: string
    turn_id: number
    codice: string
    impianto: string
  }>("/pdc-turn", data)
}

export async function updatePdcTurn(turnId: number, data: PdcTurnInput) {
  return api.put<{
    status: string
    old_turn_id: number
    new_turn_id: number
    codice: string
  }>(`/pdc-turn/${turnId}`, data)
}

export async function deletePdcTurn(turnId: number) {
  return api.delete<{ status: string; turn_id: number }>(`/pdc-turn/${turnId}`)
}

// ── Calendario italiano ──

export interface CalendarPeriodicity {
  date: string
  letter: string
  weekday: string
  is_holiday: boolean
  holiday_name: string | null
  local: string | null
}

export async function getCalendarPeriodicity(dateStr: string, local?: string) {
  const qs = new URLSearchParams({ date_str: dateStr })
  if (local) qs.append("local", local)
  return api.get<CalendarPeriodicity>(
    `/italian-calendar/periodicity?${qs.toString()}`
  )
}

// ── Lookup treno nel giro materiale (per builder PdC) ──

export interface TrainLookup {
  found: boolean
  train_id: string
  from_station?: string
  to_station?: string
  dep_time?: string
  arr_time?: string
  material_turn_id?: number | null
  is_deadhead?: boolean
  other_matches?: number
}

export async function lookupTrainInGiroMateriale(trainId: string) {
  return api.get<TrainLookup>(
    `/pdc-builder/lookup-train/${encodeURIComponent(trainId)}`
  )
}

// ── Find return trip via ARTURO Live ──
// (campi mappati 1:1 sulla risposta del backend /vt/find-return)

export interface ReturnTrain {
  train_number: string
  category?: string
  from_station: string         // stazione di partenza dell'utente
  to_station: string           // deposito di arrivo
  dep_time: string             // orario partenza dalla stazione corrente
  arr_time: string             // orario arrivo al deposito
  arr_time_real?: string
  delay?: number
  delay_arr?: number
  platform?: string
  destination_finale?: string  // capolinea finale del treno
  origin_treno?: string
  running?: boolean
  operator?: string
  source?: "arrivi" | "partenze"
}

export async function findReturnTrain(
  fromStation: string,
  toStation: string,
  afterTime = "00:00",
) {
  const qs = new URLSearchParams({
    from_station: fromStation,
    to_station: toStation,
    after_time: afterTime,
  })
  return api.get<{
    return_trains: ReturnTrain[]
    error?: string
  }>(`/vt/find-return?${qs.toString()}`)
}

// ── Triple-check treno: DB interno + PdC + ARTURO Live ────────────
export interface TrainCheckResult {
  train_id: string
  db_internal: {
    found: boolean
    data: {
      from_station: string
      dep_time: string
      to_station: string
      arr_time: string
      material_turn_id?: number
      day_index?: number
      is_deadhead?: boolean
      giro_chain_len?: number
    } | null
  }
  pdc: {
    found: boolean
    results: Array<{
      turn_id: number
      codice: string
      impianto: string
      day_number: number
      periodicita: string
      block_start: string
      block_end: string
      from_station: string
      to_station: string
    }>
  }
  arturo_live: {
    found: boolean
    data: {
      operator: string
      category: string
      origin: string
      destination: string
      dep_time: string
      arr_time: string
      num_stops: number
      delay: number
      is_trenord: boolean
      status: string
    } | null
  }
}

export async function trainCheck(trainId: string) {
  return api.get<TrainCheckResult>(`/train-check/${encodeURIComponent(trainId)}`)
}

// ── Cross-reference treno: contesto giro materiale (prev/next/chain) + PdC ──
// Endpoint backend: /train/{id}/cross-ref — vedi api/trains.py
// Complementare a trainCheck(): mentre quest'ultimo fa triple-check DB/PdC/ARTURO,
// trainCrossRef() focalizza sulla CONTINUAZIONE del giro materiale (quale
// treno precede/segue questo nel ciclo) + lista esaustiva di tutti i turni
// PdC che guidano il treno. Serve al pannello "Cross-link" nel BlockDetailModal.
export interface TrainCrossRef {
  train_id: string
  material: {
    turn_number: string | null
    material_type: string
    position: number            // -1 se non in giro
    total: number
    prev: {
      train_id: string
      from_station: string
      to_station: string
      dep_time: string
      arr_time: string
      is_deadhead: boolean
    } | null
    next: {
      train_id: string
      from_station: string
      to_station: string
      dep_time: string
      arr_time: string
      is_deadhead: boolean
    } | null
    chain: Array<{
      train_id: string
      from: string
      to: string
      dep: string
      arr: string
    }>
  }
  pdc_carriers: Array<{
    turn_id: number | null
    codice: string
    impianto: string
    profilo: string
    day_id: number | null
    day_number: number | null
    periodicita: string
    day_start: string
    day_end: string
    block_id: number | null
    block_seq: number | null
    block_start: string
    block_end: string
    from_station: string
    to_station: string
  }>
  pdc_count: number
}

export async function trainCrossRef(trainId: string) {
  return api.get<TrainCrossRef>(`/train/${encodeURIComponent(trainId)}/cross-ref`)
}

// ────────────────────────────────────────────────────────────────
// Dashboard
// ────────────────────────────────────────────────────────────────

export interface DashboardKpi {
  totale_turni: number
  turni_settimana: number
  giorni_lavorati: number
  giorni_max: number
  ore_settimana_min: number
  ore_max_min: number
  delta_30gg_pct: number | null
}

export async function getDashboardKpi() {
  return api.get<DashboardKpi>(`/api/dashboard/kpi`)
}

export interface ActivityItem {
  id: number | null
  type: "edit" | "validate" | "import" | "conflict"
  title: string
  subtitle: string
  created_at: string | null
}

export async function getActivityRecent(limit = 20) {
  return api.get<{ items: ActivityItem[]; count: number }>(
    `/api/activity/recent?limit=${limit}`,
  )
}

export interface LineaAttivaRow {
  treno: string
  tratta: string
  stato: "ok" | "ritardo" | "soppresso"
  ritardo_min: number
  ritardo_label: string
  origine: string
  destinazione: string
}

export async function getLineaAttiva() {
  return api.get<{
    items: LineaAttivaRow[]
    count: number
    cached_at: string | null
    note: string | null
  }>(`/api/linea/attiva`)
}

// ────────────────────────────────────────────────────────────────
// Auto-builder (pipeline materiale → PdC auto-generato)
// ────────────────────────────────────────────────────────────────

export interface BuildAutoRequest {
  deposito: string
  days: number // numero giornate lavorative
  day_type?: "LV" | "SAB" | "DOM" // backend default "LV"; in futuro auto dal calendario
  accessory_type?: string
}

export interface BuildAutoEntry {
  type: "TURN" | "REST"
  day: number | null
  summary?: {
    prestazione: string
    prestazione_min: number
    condotta: string
    condotta_min: number
    accessori_min: number
    tempi_medi_min: number
    extra_min: number
    meal_min: number
    meal_start: string
    meal_end: string
    presentation_time: string
    end_time: string
    day_type: string
    night_minutes: number
    is_fr: boolean
    last_station: string
    segments_count: number
    segments: TrainSegment[]
    timeline: TimelineBlock[]
    violations: Array<{ rule: string; message: string; severity: string }>
  }
}

export interface BuildAutoResponse {
  workdays_requested: number
  calendar: BuildAutoEntry[]
  deposito: string
  reachable_stations: string[]
  total_violations: number
  train_dedup: {
    total_trains: number
    unique_trains: number
    duplicates: Record<string, number>
    clean: boolean
  }
}

export async function buildAuto(req: BuildAutoRequest) {
  return api.post<BuildAutoResponse>(`/build-auto`, req)
}
