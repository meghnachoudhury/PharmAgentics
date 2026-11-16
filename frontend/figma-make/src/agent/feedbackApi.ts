// UAT feedback (core-008): the session rating and the platform questionnaire.
// Same-origin calls with the session cookie; a failed save is shown to the person, never swallowed.
export type Rating = "good" | "fine" | "bad"
export type PulseWhere = "briefing" | "forecast" | "approved" | "other"
export type FeedbackStatus = {
  pulse: { rating: Rating; at: string } | null
  survey: { submitted_at: string | null; version: number | null }
  questionnaire_version: number
}
export type QOption = { value: string; label: string }
export type QItem = {
  id: string
  type: "agree5" | "nps" | "choice" | "multi" | "text"
  text: string
  reverse?: boolean
  options?: QOption[]
  max?: number
  low?: string
  high?: string
}
export type Questionnaire = {
  id: string
  version: number
  title: string
  intro: string
  scale: { agree5: string[] }
  sections: { id: string; title: string; items: QItem[] }[]
}
export type MySurvey = { version: number | null; answers: Record<string, unknown>; submitted_at: string | null }
export type Answers = Record<string, number | string | string[]>

const BASE = (import.meta.env.VITE_PHARMAGENTICS_API_BASE_URL || "").trim().replace(/\/+$/, "")

function isObject(v: unknown): v is Record<string, unknown> {
  return v !== null && typeof v === "object" && !Array.isArray(v)
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  if (!BASE) throw new Error("API URL is not configured. Set VITE_PHARMAGENTICS_API_BASE_URL.")
  let response: Response
  try { response = await fetch(`${BASE}${path}`, { cache: "no-store", credentials: "same-origin", ...init }) }
  catch { throw new Error("Cannot reach PharmAgentics. Check your connection and try again.") }
  if (!response.ok) {
    let detail = `Feedback request failed (HTTP ${response.status})`
    try {
      const body: unknown = await response.json()
      if (isObject(body) && typeof body.detail === "string") detail = body.detail
    } catch { /* keep the status text */ }
    throw new Error(detail)
  }
  return await response.json() as T
}
const post = (body: unknown): RequestInit => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })

export async function getFeedbackStatus(): Promise<FeedbackStatus> {
  const v: unknown = await api("/api/feedback/status")
  if (!isObject(v) || !isObject(v.survey) || typeof v.questionnaire_version !== "number") throw new Error("The feedback service answered in an unexpected way.")
  return v as unknown as FeedbackStatus
}
export async function sendPulse(body: { rating: Rating; comment?: string; where?: PulseWhere; ref?: string }): Promise<{ rating: Rating; at: string }> {
  const v: unknown = await api("/api/feedback/pulse", post({ ...body, comment: body.comment || null }))
  if (!isObject(v) || typeof v.rating !== "string") throw new Error("The feedback service answered in an unexpected way.")
  return v as unknown as { rating: Rating; at: string }
}
export async function getQuestionnaire(): Promise<Questionnaire> {
  const v: unknown = await api("/api/feedback/questionnaire")
  if (!isObject(v) || !Array.isArray(v.sections) || typeof v.version !== "number") throw new Error("The questionnaire is unavailable.")
  return v as unknown as Questionnaire
}
export async function getMySurvey(): Promise<MySurvey> {
  const v: unknown = await api("/api/feedback/survey")
  if (!isObject(v) || !isObject(v.answers)) throw new Error("Your earlier answers are unavailable.")
  return v as unknown as MySurvey
}
export async function sendSurvey(version: number, answers: Answers): Promise<{ submitted_at: string; answered: number }> {
  return await api("/api/feedback/survey", post({ version, answers }))
}
