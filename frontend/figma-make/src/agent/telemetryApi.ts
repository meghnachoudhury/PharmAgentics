// Evaluation telemetry: golden-set scores (GET /api/telemetry) and live use (GET /api/telemetry/usage), aggregates only.
const BASE = (import.meta.env.VITE_PHARMAGENTICS_API_BASE_URL || "").trim().replace(/\/+$/, "")

export type TelemetryRun = {
  run_id: string; started: string; minutes: number | null; system: string; model: string | null; lane: string
  control: boolean; cases: number; reruns: number; judge: string; code_version: string; data_version: string
  metrics: Record<string, number>; judge_metrics: Record<string, number>
}
export type Telemetry = { exported: string | null; note: string; latest: TelemetryRun[]; runs: TelemetryRun[] }

export type Spread = { n: number; p50: number | null; p95: number | null } | null
export type LaneUsage = {
  requests: number; opens: number; reviews: number; insights?: number; submissions?: number
  weekly: Record<string, number>; decisions: Record<string, number>; votes: { up: number; down: number }
  engines?: Record<string, number>; scripted_ms?: Spread; agent_jobs?: Record<string, number>; agent_seconds?: Spread
}
export type Usage = {
  since: string | null; participants: number; excluded_test_records: number; computed: string
  lanes: Partial<Record<"briefing" | "forecast", LaneUsage>>
  sessions: Record<string, number>
  sus: { n: number; mean: number; median: number; min: number; max: number } | null
  cloud_seconds?: { used: number; limit: number }
}

function isObject(v: unknown): v is Record<string, unknown> {
  return v !== null && typeof v === "object" && !Array.isArray(v)
}

async function api(path: string): Promise<unknown> {
  if (!BASE) throw new Error("API URL is not configured. Set VITE_PHARMAGENTICS_API_BASE_URL.")
  let response: Response
  try { response = await fetch(`${BASE}${path}`, { cache: "no-store", credentials: "same-origin" }) }
  catch { throw new Error("Cannot reach PharmAgentics. Check your connection and try again.") }
  if (!response.ok) {
    let detail = `Telemetry request failed (HTTP ${response.status})`
    try {
      const body: unknown = await response.json()
      if (isObject(body) && typeof body.detail === "string") detail = body.detail
    } catch { /* keep the status text */ }
    throw new Error(detail)
  }
  return await response.json()
}

export async function getTelemetry(): Promise<Telemetry> {
  const v = await api("/api/telemetry")
  if (!isObject(v) || !Array.isArray(v.latest) || !Array.isArray(v.runs)) throw new Error("The telemetry service answered in an unexpected way.")
  return v as unknown as Telemetry
}

export async function getUsage(): Promise<Usage> {
  const v = await api("/api/telemetry/usage")
  if (!isObject(v) || !isObject(v.lanes) || !isObject(v.sessions)) throw new Error("The telemetry service answered in an unexpected way.")
  return v as unknown as Usage
}
