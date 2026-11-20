// core-008 FR-021: the Feedback review list. Tester admin only; the server answers 404 to anyone else.
import { api, post } from "./briefingApi"

export type Proposal = {
  id: string
  kind: "lesson" | "case"
  status: "proposed" | "approved" | "rejected" | "promoted"
  confident: boolean
  reasons: string[]
  source: string
  text?: string
  question?: string
  comment?: string
  after?: string
  reviewer_reason?: string
  draft_case?: Record<string, unknown>
  created_at: string
  decided_by: string | null
  decided_at: string | null
  note: string | null
}

export const listProposals = () => api<Proposal[]>("/api/review/proposals")
export const decideProposal = (id: string, decision: "approve" | "reject", note?: string) =>
  api<Proposal>(`/api/review/proposals/${encodeURIComponent(id)}`, post({ decision, note: note || null }))
