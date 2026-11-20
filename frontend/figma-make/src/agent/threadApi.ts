// brief-006: follow-up threads on a brief. Analysts only; the server answers 404 to anyone else.
import { api, post, type Claim, type Evidence } from "./briefingApi"

export type Offer = { brand?: string; territory?: string; week?: string; agent?: boolean } | null
export type Turn = {
  n: number
  question: string
  section: string | null
  answer: string
  claims: Claim[]
  evidence: Evidence[]
  cited: string[]
  offer: Offer
  engine: "scripted" | "agent"
  kind: string
  seconds: number
  at: string
}
export type Thread = {
  brief_id: string
  owner: string
  mine: boolean
  saved: boolean
  shared_from: string | null
  turns: Turn[]
  max_turns: number
  share_path: string | null
  suggestions: Record<string, string[]>
}

const base = (id: string) => `/api/briefing/${encodeURIComponent(id)}/thread`
export const getThread = (id: string) => api<Thread>(base(id))
export const askThread = (id: string, question: string, section?: string | null) =>
  api<Thread>(`${base(id)}/ask`, post({ question, section: section ?? null }))
export const saveThread = (id: string) => api<Thread>(`${base(id)}/save`, post({}))
export const openShared = (id: string, owner: string) => api<Thread>(`${base(id)}/shared/${encodeURIComponent(owner)}`)
export const continueShared = (id: string, owner: string) => api<Thread>(`${base(id)}/continue/${encodeURIComponent(owner)}`, post({}))

// A share link opens the brief and the saved thread: #thread=<brief id>/<owner>
export function shareLink(t: Thread): string {
  return `${window.location.origin}${window.location.pathname}#thread=${t.brief_id}/${t.owner}`
}
export function sharedFromLocation(): { briefId: string; owner: string } | null {
  const m = window.location.hash.match(/^#thread=(b-[0-9a-f]{12})\/([0-9a-f]{12})$/)
  return m ? { briefId: m[1], owner: m[2] } : null
}
