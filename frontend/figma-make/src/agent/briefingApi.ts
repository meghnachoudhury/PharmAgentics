// Exact TypeScript representation of the Briefing API contracts (core-007: roles and views).
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
export type ReviewStatus = "pending" | "approved" | "rejected"
export type BriefingResult = {
  brief_id: string
  view: "analyst"
  status: "draft_requires_review"
  review_status: ReviewStatus
  reviewed_at: string | null
  review_reason: string | null
  engine: "scripted" | "agent"
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
  triage?: TriageRecord | null  // brief-002: who made each triage call (analyst view only)
  flow?: Stage[] | null         // brief-002: the seven stages, run states and actors (analyst view only)
}
// brief-002 Phase A: the code triage plan P1 reviews, and how a brief was made.
export type StoryCard = {
  id: string
  kind: "territory" | "plan" | "competitor"
  title: string
  rank: number
  proposed: "investigate" | "over_cap"
  territory?: string | null
  manager?: { keep: boolean; position: number | null; why: string | null; hypotheses: string[] }  // agent plans only
  what_moved: string
  decision: string
  population: string
  granularity: string
  time: string
}
export type TriagePlan = {
  plan_id: string
  question: string
  data_version: string
  state: "TRIAGE_REVIEW" | "ROUTINE" | "CALENDAR" | "OUT_OF_SCOPE"
  engine?: "agent"
  model?: string
  scope?: string
  manager_order?: string[]
  manager_note?: string
  flagged?: boolean
  flags?: string[]
  weeks: string[]
  baseline: string[]
  context: string
  stories: StoryCard[]
  dropped: { territory: string; reason: string; layer: "code" }[]
  claims: Claim[]
  evidence: Evidence[]
  brand_id: string
  territory_id: string
  week_start: string
}
export type TriageDecision = { plan_id: string; stories: string[] }
export type AgentStatus = { online: boolean; configured: boolean; model: string | null; queued: number; running: number; last_seen_seconds: number | null }
export type AgentJob = { id: string; kind: "triage" | "brief"; status: "queued" | "running" | "done" | "failed"; error: string | null; result?: unknown }
export type TriageRecord = {
  plan_id: string
  default: boolean
  order: string[]
  calls: { story: string; title: string; outcome: string; layer: "code" | "agent" | "human"; position?: number; why?: string | null }[]
}
export type Stage = {
  stage: number
  name: string
  actors: { kind: "code" | "agent" | "llm" | "human"; name: string }[]
  states: string[]
  note: string
}
// The leadership view: an executive summary cut from the answer by the server. It never
// carries claims, evidence, query text or a trace.
export type LeadershipBrief = {
  brief_id: string
  view: "leadership"
  engine: "scripted"
  system: string
  brand_id: string
  territory_id: string
  week_start: string
  data_version: string | null
  abstained: boolean
  review_status: ReviewStatus
  reviewed_at: string | null
  summary: string
}
export type PublishedBrief = {
  brief_id: string
  week_start: string
  territory_id: string
  engine: string
  reviewed_at: string | null
  abstained: boolean
}
export type LaneRole = {
  role: string
  persona: string
  label: string
  views: ("analyst" | "leadership")[]
  actions: string[]
  available: boolean
}
export type Me = { name: string; auth_mode: "oidc" | "dev"; lanes: { briefing?: LaneRole; forecast?: LaneRole } }
export type BriefingQuery = {
  intent: "weekly_brief"
  brand_id: string
  territory_id: string
  week_start: string
  question: string
}

export class NotSignedIn extends Error {}

const BASE = (import.meta.env.VITE_PHARMAGENTICS_API_BASE_URL || "").trim().replace(/\/+$/, "")

function expectObject(v: unknown): asserts v is Record<string, unknown> {
  if (v === null || typeof v !== "object" || Array.isArray(v)) throw new Error("Invalid API response object")
}
function stringArray(v: unknown): v is string[] {
  return Array.isArray(v) && v.every(x => typeof x === "string")
}
const REVIEW = new Set(["pending", "approved", "rejected"])

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  if (!BASE) throw new Error("API URL is not configured. Set VITE_PHARMAGENTICS_API_BASE_URL. No mock fallback is enabled.")
  let response: Response
  try { response = await fetch(`${BASE}${path}`, { cache: "no-store", credentials: "same-origin", ...init }) }
  catch { throw new Error("Cannot reach Briefing API. Check server, HTTPS/CORS settings, and API URL.") }
  if (response.status === 401) throw new NotSignedIn("Sign in first.")
  if (!response.ok) {
    let message = `Briefing API returned HTTP ${response.status}`
    try {
      const payload: unknown = await response.json()
      expectObject(payload)
      if (typeof payload.detail === "string") message = payload.detail
    } catch { /* keep status */ }
    throw new Error(message)
  }
  if (response.status === 204) return undefined as T
  return await response.json() as T
}
const post = (body: unknown): RequestInit => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })

export async function getMe(): Promise<Me> {
  const v: unknown = await api("/api/me")
  expectObject(v)
  if (typeof v.name !== "string" || (v.auth_mode !== "oidc" && v.auth_mode !== "dev")) throw new Error("The backend identity contract is incompatible with this frontend.")
  expectObject(v.lanes)
  return v as unknown as Me
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
function checkAnalyst(v: unknown): BriefingResult {
  expectObject(v)
  if (v.view !== "analyst" || typeof v.brief_id !== "string" || v.status !== "draft_requires_review" || (v.engine !== "scripted" && v.engine !== "agent") ||
      !REVIEW.has(v.review_status as string) || typeof v.answer !== "string" ||
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
function checkLeadership(v: unknown): LeadershipBrief {
  expectObject(v)
  if (v.view !== "leadership" || typeof v.brief_id !== "string" || typeof v.summary !== "string" ||
      "claims" in v || "evidence" in v || "answer" in v) {
    throw new Error("Backend returned a leadership view that is not a plain executive summary.")
  }
  return v as unknown as LeadershipBrief
}
export async function getTriage(q: BriefingQuery): Promise<TriagePlan> {
  return checkPlan(await api("/api/briefing/triage", post(q)))
}
function checkPlan(v: unknown): TriagePlan {
  expectObject(v)
  if (typeof v.plan_id !== "string" || !["TRIAGE_REVIEW", "ROUTINE", "CALENDAR", "OUT_OF_SCOPE"].includes(v.state as string) ||
      !Array.isArray(v.stories) || !Array.isArray(v.dropped) || !Array.isArray(v.claims) || !Array.isArray(v.evidence)) {
    throw new Error("Backend returned a triage plan incompatible with this frontend.")
  }
  const ids = new Set((v.evidence as { id: string }[]).map(e => e.id))
  if ((v.claims as Claim[]).some(c => !ids.has(c.evidence_id))) throw new Error("The triage plan contains a claim without a resolvable evidence record")
  for (const c of v.stories as unknown[]) {
    expectObject(c)
    if (typeof c.id !== "string" || (c.proposed !== "investigate" && c.proposed !== "over_cap") ||
        ["what_moved", "decision", "population", "granularity", "time"].some(k => typeof c[k] !== "string")) {
      throw new Error("A triage card is incompatible with this frontend.")
    }
  }
  return v as unknown as TriagePlan
}
export async function getBriefing(q: BriefingQuery, triage?: TriageDecision): Promise<BriefingResult> {
  return checkAnalyst(await api("/api/briefing/query", post(triage ? { ...q, triage } : q)))
}
export async function openBrief(id: string, view: "analyst"): Promise<BriefingResult>
export async function openBrief(id: string, view: "leadership"): Promise<LeadershipBrief>
export async function openBrief(id: string, view: "analyst" | "leadership"): Promise<BriefingResult | LeadershipBrief> {
  const v: unknown = await api(`/api/briefing/${encodeURIComponent(id)}?view=${view}`)
  return view === "analyst" ? checkAnalyst(v) : checkLeadership(v)
}
export async function listPublished(): Promise<PublishedBrief[]> {
  const v: unknown = await api("/api/briefing/published")
  if (!Array.isArray(v)) throw new Error("The backend published-briefs contract is incompatible with this frontend.")
  return v as PublishedBrief[]
}
export async function reviewBrief(id: string, decision: "approved" | "rejected", reason?: string): Promise<BriefingResult> {
  return checkAnalyst(await api(`/api/briefing/${encodeURIComponent(id)}/review`, post({ decision, reason: reason || null })))
}
export async function markInsight(id: string, view: "analyst" | "leadership"): Promise<void> {
  await api("/api/uat/insight", post({ brief_id: id, view }))
}

// Agent jobs (core-007 FR-028): run by the owner's local worker; the app only queues and checks them.
export async function getAgentStatus(): Promise<AgentStatus> {
  return await api("/api/agent/status") as AgentStatus
}
export async function submitAgentJob(req: { kind: "triage" | "brief"; query: BriefingQuery; triage_job?: string; decision?: TriageDecision }): Promise<AgentJob> {
  return await api("/api/agent/jobs", post(req)) as AgentJob
}
export async function waitAgentJob(id: string, onUpdate: (j: AgentJob) => void): Promise<AgentJob> {
  const started = Date.now()
  for (;;) {
    const job = await api(`/api/agent/jobs/${encodeURIComponent(id)}`) as AgentJob
    onUpdate(job)
    if (job.status === "done" || job.status === "failed") return job
    if (Date.now() - started > 20 * 60 * 1000) throw new Error("The agent job is taking too long; check the agent host.")
    await new Promise(r => setTimeout(r, 3000))
  }
}
export function agentPlan(job: AgentJob): TriagePlan { return checkPlan(job.result) }
export function agentBrief(job: AgentJob): BriefingResult { return checkAnalyst(job.result) }
