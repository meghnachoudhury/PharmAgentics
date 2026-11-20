// Forecast API contract. The server—not the browser—chooses the permitted view and engine.
import { NotSignedIn } from "./briefingApi"

const BASE = (import.meta.env.VITE_PHARMAGENTICS_API_BASE_URL || "").trim().replace(/\/+$/, "")

export type ForecastRequest = { territory_id: string; week_start: string; window_weeks?: number; view?: "analyst" | "leadership" }
export type ForecastCase = { case_id: string; tag: string; label: string; request: ForecastRequest }
export type ForecastContext = { territory_ids: string[]; available_weeks: string[]; latest_week: string; metric: "TRx"; brand: string }
export type ForecastSummary = { question?: string | null; job_status?: string; forecast_run_id: string; territory_id: string; week_start: string; window_weeks: number; variance_trx: number; abstained: boolean; headline: string; review_status: string; created_at: string; reviewed_at: string | null }
export type ForecastDriver = { driver: string; label?: string; territory?: string; impact_trx: number; confidence: string; confidence_reasons?: string[]; method?: string; controls?: string[]; weeks?: string[]; evidence_ids?: string[] }
export type ForecastSectionText = { id: string; title: string; text: string }
export type ForecastDecision = { by: string; action: string; target: string; reason: string }
export type ForecastCandidate = { id: string; driver: string; territory: string; label: string; first_active: string | null; last_active: string | null; status: string; reason: string | null; comparison: string | null }
export type ForecastComparison = { id: string; episode: string; method: string; controls: string[]; stats: Record<string, unknown>; flags: string[] }
export type ForecastScope = { question: string; weeks: string[]; territory: string; territory_name: string; intent: string; intent_label: string; period: string; n_weeks: number; notes: string[]; out_of_scope: string | null; engine: string; investigator?: string; read_by?: "model" | "rules" }
export type ForecastFollowupItem = { id: string; question: string; status: "running" | "done" | "failed"; op: string | null; answer: string | null; child_run_id: string | null }
export type ForecastStep = { tool: string; args: Record<string, unknown>; result: string }
export type ForecastReport = { headline: string; territory_id: string; week: number; week_ending: string; window_weeks: number; forecast_trx: number | null; actual_trx: number | null; variance_trx: number | null; variance_pct: number | null; residual_trx: number | null; drivers: ForecastDriver[]; caveats: string[]; what_to_check: { question: string; why: string; owner: string }[]; abstained: boolean; verification?: { verdict?: string; checks?: { id: string; status: string; detail: string }[] }; investigator_mode?: string
  question?: string; intent?: string; summary?: string | null; sections?: ForecastSectionText[]; decisions?: ForecastDecision[]; candidates?: ForecastCandidate[]
  comparisons?: ForecastComparison[]; summary_by?: "model" | "code"; scope_read_by?: string; set_aside_weeks?: string[]; week_start?: string | null; out_of_scope?: string; bias_trx?: number | null }
export type ForecastRun = { followups?: ForecastFollowupItem[]; parent_run_id?: string | null; kind?: "question" | "form"; job_status?: "running" | "done" | "failed"; job_error?: string | null; progress?: ForecastStep[]; view: "analyst" | "leadership"; forecast_run_id: string; review_status: string; reviewed_at: string | null; review_note: string | null; report: ForecastReport; stages?: { stage: number; name: string; status: string }[]; history?: { at: string; role: string; action: string; note: string | null }[] }

function object(value: unknown): asserts value is Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid Forecast API response")
}
async function api<T>(path: string, init?: RequestInit): Promise<T> {
  if (!BASE) throw new Error("API URL is not configured. Set VITE_PHARMAGENTICS_API_BASE_URL.")
  let response: Response
  try { response = await fetch(`${BASE}${path}`, { cache: "no-store", credentials: "same-origin", ...init }) }
  catch { throw new Error("Cannot reach Forecast API. Check the server and API URL.") }
  if (response.status === 401) throw new NotSignedIn("Sign in first.")
  if (!response.ok) {
    let detail = `Forecast API returned HTTP ${response.status}`
    try { const body: unknown = await response.json(); object(body); if (typeof body.detail === "string") detail = body.detail } catch { /* retain status */ }
    throw new Error(detail)
  }
  return await response.json() as T
}
const post = (body?: unknown): RequestInit => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) })
function run(value: unknown): ForecastRun {
  object(value)
  if ((value.view !== "analyst" && value.view !== "leadership") || typeof value.forecast_run_id !== "string" || !value.report) throw new Error("Forecast response is incompatible with this frontend.")
  object(value.report)
  if (typeof value.report.headline !== "string" || !Array.isArray(value.report.drivers) || !Array.isArray(value.report.caveats)) throw new Error("Forecast report is incomplete.")
  if (value.view === "leadership" && ("stages" in value || "history" in value)) throw new Error("Leadership response contains analyst-only trace data.")
  return value as unknown as ForecastRun
}

export async function forecastCases(): Promise<ForecastCase[]> { const value: unknown = await api("/api/forecast/cases"); object(value); if (!Array.isArray(value.cases)) throw new Error("Forecast cases are unavailable."); return value.cases as ForecastCase[] }
export async function forecastContext(): Promise<ForecastContext> { const value: unknown = await api("/api/forecast/context"); object(value); if (!Array.isArray(value.territory_ids) || !Array.isArray(value.available_weeks) || typeof value.latest_week !== "string" || value.metric !== "TRx" || typeof value.brand !== "string") throw new Error("Forecast scope is unavailable."); return value as unknown as ForecastContext }
export async function createForecast(request: ForecastRequest): Promise<ForecastRun> { return run(await api("/api/forecast/runs", post(request))) }
export async function listForecasts(status?: string): Promise<ForecastSummary[]> { const value: unknown = await api(`/api/forecast/runs${status ? `?status=${encodeURIComponent(status)}` : ""}`); object(value); if (!Array.isArray(value.runs)) throw new Error("Forecast run list is unavailable."); return value.runs as ForecastSummary[] }
export async function openForecast(
  id: string,
  view?: ForecastRun["view"],
): Promise<ForecastRun> {
  const query = view ? `?view=${encodeURIComponent(view)}` : ""
  const result = run(await api(`/api/forecast/runs/${encodeURIComponent(id)}${query}`))

  if (view && result.view !== view) {
    throw new Error("The server returned a different Forecast view.")
  }

  return result
}
export async function submitForecast(id: string): Promise<ForecastRun> { return run(await api(`/api/forecast/runs/${encodeURIComponent(id)}/submit`, post())) }
export async function reviewForecast(id: string, decision: "approved" | "rejected" | "returned", note?: string): Promise<ForecastRun> { return run(await api(`/api/forecast/runs/${encodeURIComponent(id)}/review`, post({ decision, note: note || null }))) }

export type ForecastAsk = { question: string; territory_id?: string | null; week_from?: string | null; week_to?: string | null; intent?: string | null; view?: "analyst" | "leadership" }
export async function forecastScope(ask: ForecastAsk): Promise<ForecastScope> { const value: unknown = await api("/api/forecast/scope", post(ask)); object(value); if (typeof value.intent !== "string" || !Array.isArray(value.weeks)) throw new Error("The question could not be read."); return value as unknown as ForecastScope }
export async function askForecast(ask: ForecastAsk): Promise<ForecastRun> { return run(await api("/api/forecast/ask", post(ask))) }
export async function askFollowup(id: string, question: string): Promise<ForecastRun> { return run(await api(`/api/forecast/runs/${encodeURIComponent(id)}/followups`, post({question}))) }
export type DriverProbe = { id: string; question: string; expect: string[]; got: string[]; seconds: number | null }
export type DriverSystem = { run_id: string; model: string | null; exported: string; metrics: { driver_recall: number; false_drivers: number; exact_set_share: number; probes: number }; confusion: Record<string, Record<string, number>>; drivers: string[]; probes: DriverProbe[] }
export type DriverBoard = { labels: string; systems: Record<string, DriverSystem> }
export async function forecastDrivers(): Promise<DriverBoard> { const value: unknown = await api("/api/forecast/drivers"); object(value); if (typeof value.systems !== "object" || value.systems === null) throw new Error("Driver recovery is unavailable."); return value as unknown as DriverBoard }
