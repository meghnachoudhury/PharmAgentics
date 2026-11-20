// core-008 FR-021: the Feedback review panel on the Evaluation page, for the tester admin only.
// `python -m eval improve` proposes lessons and cases; a person approves or rejects each; `eval promote` writes the
// approved ones and a pull request merges them. Nothing here changes the agents directly.
import { useEffect, useState } from "react"
import { decideProposal, listProposals, type Proposal } from "./agent/reviewApi"

function message(e: unknown): string { return e instanceof Error ? e.message : String(e) }

function Card({p, onDecided}: {p: Proposal, onDecided: (p: Proposal) => void}) {
  const [note, setNote] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const decide = async (d: "approve" | "reject") => {
    setBusy(true); setError(null)
    try { onDecided(await decideProposal(p.id, d, note.trim() || undefined)) } catch (e) { setError(message(e)) } finally { setBusy(false) }
  }
  const open = p.status === "proposed"
  return <li className="rounded-xl border border-rule bg-sheet p-4 text-sm">
    <div className="flex flex-wrap items-center gap-2 text-[11px]">
      <span className="rounded bg-paper px-2 py-0.5 font-medium uppercase tracking-wider text-muted">{p.kind}</span>
      <span className={`rounded px-2 py-0.5 font-medium ${p.confident ? "bg-okbg text-ok" : "bg-amberbg text-amber"}`}>{p.confident ? "Confident" : "Flagged"}</span>
      <span className="rounded bg-paper px-2 py-0.5 text-muted">{p.status}</span>
      <span className="ml-auto font-mono text-muted">{p.id}</span>
    </div>
    {p.text && <p className="mt-3 font-serif text-[15px] leading-relaxed text-ink">{p.text}</p>}
    {p.comment && <p className="mt-2 text-xs text-muted">From a downvote: “{p.comment}”{p.question ? ` on “${p.question}”` : ""}</p>}
    {p.kind === "case" && <p className="mt-2 text-xs text-muted">Draft case from {p.source}. Approving adds it to the drafts to label; it never counts until it has facts and a reference answer.</p>}
    {p.reasons.length > 0 && <ul className="mt-2 list-disc pl-5 text-xs text-amber">{p.reasons.map(r => <li key={r}>{r}</li>)}</ul>}
    {p.reviewer_reason && <p className="mt-2 text-xs text-muted">Agent reviewer: {p.reviewer_reason}</p>}
    {p.after && <details className="mt-2 text-xs"><summary className="cursor-pointer text-agentdeep">The rerun with this lesson</summary><pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded bg-paper p-3 font-sans text-[12px] text-ink">{p.after}</pre></details>}
    {open ? <div className="mt-3 flex flex-wrap items-center gap-2">
      <label className="sr-only" htmlFor={`note-${p.id}`}>Note</label>
      <input id={`note-${p.id}`} value={note} onChange={e => setNote(e.target.value)} maxLength={500} placeholder="Note (optional)" className="min-w-0 flex-1 rounded-lg border border-rule bg-paper px-3 py-1.5 text-xs text-ink"/>
      <button type="button" disabled={busy} onClick={() => void decide("approve")} className="rounded-lg bg-navy px-3 py-1.5 text-xs font-medium text-onaccent hover:bg-navyhover disabled:opacity-40">Approve</button>
      <button type="button" disabled={busy} onClick={() => void decide("reject")} className="rounded-lg border border-rule px-3 py-1.5 text-xs text-ink hover:bg-paper disabled:opacity-40">Reject</button>
    </div> : <p className="mt-3 text-xs text-muted">{p.status} by {p.decided_by ?? "?"}{p.note ? `: ${p.note}` : ""}</p>}
    {error && <p role="alert" className="mt-2 text-xs text-amber">{error}</p>}
  </li>
}

export function FeedbackReview() {
  const [items, setItems] = useState<Proposal[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => { listProposals().then(setItems).catch(e => setError(message(e))) }, [])
  return <section className="workspace-content space-y-4 pb-10" aria-labelledby="feedback-review">
    <div className="border-b border-rule pb-3">
      <h2 id="feedback-review" className="text-xl">Feedback review</h2>
      <p className="mt-1 text-sm text-muted">Lessons and cases proposed from votes and saved threads by <code>python -m eval improve</code>. Approving queues a proposal; <code>python -m eval promote</code> writes it and a pull request merges it.</p>
    </div>
    {error && <p role="alert" className="rounded-xl bg-amberbg px-4 py-3 text-sm text-amber">{error}</p>}
    {items && items.length === 0 && <p className="text-sm text-muted">No proposals yet.</p>}
    {items && items.length > 0 && <ul className="space-y-3">{items.map(p => <Card key={p.id} p={p} onDecided={d => setItems(xs => (xs ?? []).map(x => x.id === d.id ? d : x))}/>)}</ul>}
  </section>
}
