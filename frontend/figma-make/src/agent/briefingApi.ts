// Exact TypeScript representation of the NEW Briefing API contracts.
// Never substitute sample data if a request or contract check fails.
export type ReleaseContext = {
  first_week: string
  latest_week: string
  territory_ids: string[]
  available_weeks: string[]
  product_ids: string[]
  supported_intents: string[]
  engine: "scripted"
}
export type Evidence = {
  id: string
  tool: string
  params: Record<string, unknown>
  query: string | null
  result: unknown
  data_version: string | null
}
export type Claim = { value: string; evidence_id: string }
export type BriefingResult = {
  status: "draft_requires_review"
  review_status: "not_submitted"
  engine: "scripted"
  system: string
  question: string
  brand_id: string
  territory_id: string
  week_start: string
  answer: string
  claims: Claim[]
  evidence: Evidence[]
  data_version: string | null
  abstained: boolean
}
export type BriefingQuery = {
  intent: "weekly_brief"
  brand_id: string
  territory_id: string
  week_start: string
  question: string
}

const BASE = (import.meta.env.VITE_PHARMAGENTICS_API_BASE_URL || "").trim().replace(/\/+$/, "")

function expectObject(v: unknown): asserts v is Record<string, unknown> {
  if (v === null || typeof v !== "object" || Array.isArray(v)) throw new Error("Invalid API response object")
}
function stringArray(v: unknown): v is string[] {
  return Array.isArray(v) && v.every(x => typeof x === "string")
}
async function api<T>(path: string, init?: RequestInit): Promise<T> {
  if (!BASE) throw new Error("API URL is not configured. Set VITE_PHARMAGENTICS_API_BASE_URL. No mock fallback is enabled.")
  let response: Response
  try { response = await fetch(`${BASE}${path}`, { cache: "no-store", ...init }) }
  catch { throw new Error("Cannot reach Briefing API. Check server, HTTPS/CORS settings, and API URL.") }
  if (!response.ok) {
    let message = `Briefing API returned HTTP ${response.status}`
    try {
      const payload: unknown = await response.json()
      expectObject(payload)
      if (typeof payload.detail === "string") message = payload.detail
    } catch { /* keep status */ }
    throw new Error(message)
  }
  return await response.json() as T
}
export async function getContext(): Promise<ReleaseContext> {
  const v: unknown = await api("/api/briefing/context")
  expectObject(v)
  if (!stringArray(v.available_weeks) || !stringArray(v.territory_ids) ||
      !stringArray(v.product_ids) || !stringArray(v.supported_intents) ||
      v.engine !== "scripted" || typeof v.latest_week !== "string" || typeof v.first_week !== "string") {
    throw new Error("The backend context contract is incompatible with this frontend.")
  }
  if (!v.supported_intents.includes("weekly_brief")) throw new Error("The backend does not currently support weekly briefings.")
  if (!v.product_ids.length || !v.territory_ids.length || !v.available_weeks.length) {
    throw new Error("The backend returned no supported brands, territories or reporting weeks.")
  }
  return v as unknown as ReleaseContext
}
export async function getBriefing(q: BriefingQuery): Promise<BriefingResult> {
  const v: unknown = await api("/api/briefing/query", {
    method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(q),
  })
  expectObject(v)
  if (v.status !== "draft_requires_review" || v.engine !== "scripted" ||
      v.review_status !== "not_submitted" || typeof v.answer !== "string" ||
      !Array.isArray(v.claims) || !Array.isArray(v.evidence) || typeof v.abstained !== "boolean") {
    throw new Error("Backend returned a response incompatible with the implemented weekly briefing UI.")
  }
  const ids = new Set<string>()
  for (const ev of v.evidence as unknown[]) {
    expectObject(ev)
    if (typeof ev.id !== "string") throw new Error("Evidence identifier missing")
    ids.add(ev.id)
  }
  for (const cl of v.claims as unknown[]) {
    expectObject(cl)
    if (typeof cl.evidence_id !== "string" || typeof cl.value !== "string" || !ids.has(cl.evidence_id)) {
      throw new Error("Backend contains a claim without a resolvable evidence record")
    }
  }
  return v as unknown as BriefingResult
}
