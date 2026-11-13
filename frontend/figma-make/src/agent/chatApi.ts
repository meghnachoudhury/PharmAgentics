import {NotSignedIn, type Claim, type Evidence} from './briefingApi'

export type ChatLane = 'briefing' | 'forecast'
export type ChatIntent = 'metric' | 'share' | 'change' | 'health' | 'forecast' | 'drivers' | 'residual' | 'verification' | 'next' | 'summary' | 'review' | 'evidence' | 'definition'
export type ChatScope = {territory_id: string; week_start: string; window_weeks: number}
export type ChatRecord = ChatScope & {id: string; review_status: string}
export type ChatContext = {lane: ChatLane; view: 'analyst' | 'leadership'; live_metrics: boolean; weeks: string[]; territories: string[]; latest_week: string | null; records: ChatRecord[]}
export type ChatRequest = Partial<ChatScope> & {lane: ChatLane; question: string; record_id?: string; previous_intent?: ChatIntent; metric?: 'trx' | 'nrx' | 'nbrx'}
export type ChatAnswer = {lane: ChatLane; view: 'analyst' | 'leadership'; engine: 'governed_queries'; status: 'answered' | 'unsupported' | 'needs_report'; answer: string; intent: ChatIntent | null; metric: 'trx' | 'nrx' | 'nbrx'; scope?: ChatScope; record_id?: string; review_status?: string; data_version?: string | null; claims?: Claim[]; evidence?: Evidence[]; citations?: {start: number; end: number; claim: number}[]}

const BASE = (import.meta.env.VITE_PHARMAGENTICS_API_BASE_URL || '').trim().replace(/\/+$/, '')
async function api(path: string, body?: ChatRequest): Promise<unknown> {
  if (!BASE) throw new Error('API URL is not configured. Set VITE_PHARMAGENTICS_API_BASE_URL.')
  let response: Response
  try {
    response = await fetch(`${BASE}/api/chat/${path}`, {credentials: 'same-origin', cache: 'no-store',
      ...(body ? {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)} : {})})
  } catch {throw new Error('Cannot reach PharmAgentics. Your question was not answered. Try again when the connection returns.')}
  if (response.status === 401) throw new NotSignedIn('Sign in again to ask a question.')
  if (!response.ok) {
    const detail = await response.json().catch(()=>null)
    throw new Error(typeof detail?.detail === 'string' ? detail.detail : `Question request failed (HTTP ${response.status}).`)
  }
  return response.json()
}
function object(v: unknown): asserts v is Record<string, unknown> {
  if (!v || typeof v !== 'object' || Array.isArray(v)) throw new Error('Invalid question API response.')
}
export async function getChatContext(lane: ChatLane): Promise<ChatContext> {
  const v = await api(`context?lane=${encodeURIComponent(lane)}`)
  object(v)
  if (v.lane !== lane || !['analyst', 'leadership'].includes(String(v.view)) ||
      typeof v.live_metrics !== 'boolean' || !Array.isArray(v.weeks) || !Array.isArray(v.territories) || !Array.isArray(v.records)) {
    throw new Error('The question workspace context is incompatible with this frontend.')
  }
  return v as unknown as ChatContext
}
export async function askQuestion(request: ChatRequest): Promise<ChatAnswer> {
  const v = await api('query', request)
  object(v)
  if (v.lane !== request.lane || typeof v.answer !== 'string' || v.engine !== 'governed_queries' ||
      !['answered', 'unsupported', 'needs_report'].includes(String(v.status)) || !['analyst', 'leadership'].includes(String(v.view))) {
    throw new Error('The answer is incompatible with this frontend.')
  }
  if (v.view === 'leadership' && ['claims','evidence','citations','query','stages','trace'].some(k=>k in v)) {
    throw new Error('A leadership answer included restricted analyst data.')
  }
  if (v.claims !== undefined || v.evidence !== undefined) {
    if (!Array.isArray(v.claims) || !Array.isArray(v.evidence)) throw new Error('The answer has incomplete source records.')
    const ids = new Set(v.evidence.map(e=>e?.id))
    if (v.claims.some(c=>typeof c?.value !== 'string' || !ids.has(c?.evidence_id))) throw new Error('The answer has an unsupported numeric claim.')
  }
  return v as unknown as ChatAnswer
}
