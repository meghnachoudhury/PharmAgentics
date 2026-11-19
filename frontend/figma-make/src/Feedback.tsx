// UAT feedback (core-008): under every generated answer, thumbs up or down and the session rating
// (good, fine, bad); and the platform questionnaire, opened from the sidebar or the account menu.
// The server stores everything under a pseudonymous ID; this file only collects it and shows what has been given.
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react"
import { toast } from "sonner"
import {
  getFeedbackStatus, getMyVote, getMySurvey, getQuestionnaire, sendPulse, sendSurvey, sendVote,
  type AnswerLane, type AnswerView, type Answers, type FeedbackStatus, type PulseWhere, type QItem, type Questionnaire,
  type Rating, type Vote,
} from "./agent/feedbackApi"

const message = (e: unknown) => e instanceof Error ? e.message : String(e)
const LABEL: Record<Rating, string> = { good: "Good", fine: "Fine", bad: "Bad" }
const TONE: Record<Rating, string> = { good: "text-ok", fine: "text-amber", bad: "text-neg" }
const BG: Record<Rating, string> = { good: "bg-okbg", fine: "bg-amberbg", bad: "bg-warnbg" }
const RATINGS: Rating[] = ["good", "fine", "bad"]

function Face({ kind, className = "h-5 w-5" }: { kind: Rating; className?: string }) {
  const mouth = kind === "good" ? "M8 14.5c1 1.4 2.3 2 4 2s3-.6 4-2" : kind === "fine" ? "M8.5 15.5h7" : "M8 16.5c1-1.4 2.3-2 4-2s3 .6 4 2"
  return <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="12" cy="12" r="9" /><path d="M9 10h.01M15 10h.01" /><path d={mouth} />
  </svg>
}

type Ctx = {
  status: FeedbackStatus | null
  openSurvey: () => void
  signOut: () => void
  setPulse: (p: { rating: Rating; at: string }) => void
  where: PulseWhere
}
const FeedbackCtx = createContext<Ctx | null>(null)
function useFeedback(): Ctx {
  const c = useContext(FeedbackCtx)
  if (!c) throw new Error("Feedback controls must be used inside FeedbackProvider")
  return c
}
// For the account menu: open the questionnaire, sign out, and whether the questionnaire is done.
export function useFeedbackActions() {
  const f = useFeedback()
  return { openSurvey: f.openSurvey, signOut: f.signOut, surveyDone: Boolean(f.status?.survey.submitted_at) }
}

export function FeedbackProvider({ where, children }: { where: PulseWhere; children: ReactNode }) {
  const [status, setStatus] = useState<FeedbackStatus | null>(null)
  const [surveyOpen, setSurveyOpen] = useState(false)
  const refresh = useCallback(() => { getFeedbackStatus().then(setStatus).catch(() => setStatus(null)) }, [])
  useEffect(() => { refresh() }, [refresh])
  const ctx = useMemo<Ctx>(() => ({
    status, where,
    openSurvey: () => setSurveyOpen(true),
    signOut: () => window.location.assign("/auth/logout"),  // never asks for a rating (core-008 FR-003)
    setPulse: p => setStatus(s => s ? { ...s, pulse: p } : s),
  }), [status, where])
  return <FeedbackCtx.Provider value={ctx}>
    {children}
    {surveyOpen && <SurveyModal onClose={() => setSurveyOpen(false)} onSubmitted={refresh} />}
  </FeedbackCtx.Provider>
}

// The questionnaire invitation, quietly, at the foot of the sidebar: a dot until it is answered.
export function ShareFeedbackLink({ expanded, onOpen }: { expanded: boolean; onOpen?: () => void }) {
  const f = useFeedback()
  const pending = Boolean(f.status && !f.status.survey.submitted_at)
  return <button type="button" onClick={() => { onOpen?.(); f.openSurvey() }} title="Share feedback about PharmAgentics"
    className="relative flex w-full items-center gap-3 rounded-xl px-[10px] py-2 text-left text-xs text-muted transition hover:bg-paper/60 hover:text-ink">
    <span className="relative shrink-0">
      <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12Z" /></svg>
      {pending && <span aria-hidden="true" className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-agent ring-2 ring-sheet" />}
    </span>
    <span className={expanded ? "whitespace-nowrap" : "sr-only"}>Share feedback{pending ? " (5 minutes)" : ""}</span>
  </button>
}

// --- under one answer: the mistakes notice, thumbs up or down, and the session rating -------------

const THUMB = "M7 10v12M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2a3.13 3.13 0 0 1 3 3.88Z"
function Thumb({ down = false }: { down?: boolean }) {
  return <svg viewBox="0 0 24 24" className={`h-4 w-4 ${down ? "rotate-180" : ""}`} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={THUMB} /></svg>
}

export function AnswerFeedback({ lane, refId, view }: { lane: AnswerLane; refId: string; view: AnswerView }) {
  const [vote, setVote] = useState<Vote | null>(null)
  const [comment, setComment] = useState("")
  const [saved, setSaved] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    let live = true
    setVote(null); setComment(""); setSaved(""); setError(null)
    getMyVote(lane, refId, view).then(v => { if (live) { setVote(v.vote); setComment(v.comment ?? ""); setSaved(v.comment ?? "") } })
      .catch(() => { /* showing an earlier vote is a convenience; voting still reports its own errors */ })
    return () => { live = false }
  }, [lane, refId, view])
  const send = async (v: Vote, note: string) => {
    setBusy(true); setError(null)
    try {
      const r = await sendVote({ lane, ref: refId, view, vote: v, comment: note.trim() || undefined })
      setVote(r.vote); setSaved(r.comment ?? ""); setComment(r.comment ?? "")
      toast.success(note.trim() ? "Comment saved. Thank you." : "Thanks for rating this answer.")
    }
    catch (e) { setError(message(e)) }
    finally { setBusy(false) }
  }
  const thumb = (v: Vote) => `grid h-9 w-9 place-items-center rounded-lg ring-1 transition disabled:opacity-60 ${vote === v ? (v === "up" ? "bg-okbg text-ok ring-ok/40" : "bg-amberbg text-amber ring-amber/40") : "text-muted ring-rule hover:bg-paper hover:text-ink"}`
  const noted = vote !== null && saved === comment.trim() && saved !== ""
  return <div className="space-y-3 rounded-xl bg-sheet px-5 py-4 border border-rule">
    <p className="text-xs text-muted">PharmAgentics can make mistakes. Check important figures {view === "leadership" ? "with the Commercial Analyst" : "against the evidence"}.</p>
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-rule pt-3">
      <span className="text-sm text-ink">{vote ? "Thanks for rating this answer" : "Was this answer right?"}</span>
      <div role="group" aria-label="Rate this answer" className="flex items-center gap-2">
        <button type="button" aria-pressed={vote === "up"} aria-label="Thumbs up" title="Good answer" disabled={busy || vote === "up"} onClick={() => void send("up", "")} className={thumb("up")}><Thumb /></button>
        <button type="button" aria-pressed={vote === "down"} aria-label="Thumbs down" title="Something is wrong" disabled={busy || vote === "down"} onClick={() => void send("down", "")} className={thumb("down")}><Thumb down /></button>
      </div>
    </div>
    {vote && <div className="flex flex-col gap-2 sm:flex-row sm:items-start">
      <label className="sr-only" htmlFor={`vote-note-${refId}-${view}`}>{vote === "down" ? "What was wrong?" : "What worked?"}</label>
      <textarea id={`vote-note-${refId}-${view}`} value={comment} onChange={e => setComment(e.target.value)} maxLength={500} rows={2}
        placeholder={vote === "down" ? "What was wrong? (optional, no names please)" : "What worked? (optional, no names please)"}
        className="min-w-0 flex-1 rounded-xl border border-rule bg-paper p-2.5 text-sm" />
      <button type="button" disabled={busy || noted || !comment.trim()} onClick={() => void send(vote, comment)}
        className="rounded-lg px-3 py-2 text-xs font-semibold text-agentdeep border border-rule hover:bg-paper disabled:text-muted disabled:opacity-60">{noted ? "Comment saved" : "Send comment"}</button>
    </div>}
    {error && <p role="alert" className="text-xs text-amber">{error}</p>}
    <SessionRating refId={refId} />
  </div>
}

// How the session is going, asked next to the work it is about (core-008 FR-003). Shrinks once given.
function SessionRating({ refId }: { refId: string }) {
  const f = useFeedback()
  const current = f.status?.pulse?.rating ?? null
  const [editing, setEditing] = useState(false)
  const [comment, setComment] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  if (!f.status) return null  // the feedback service is unavailable: say nothing rather than offer a broken control
  const send = async (rating: Rating, note?: string) => {
    setBusy(true); setError(null)
    try {
      f.setPulse(await sendPulse({ rating, comment: note?.trim() || undefined, where: f.where, ref: refId }))
      toast.success(note?.trim() ? "Note saved. Thank you." : `Session rated ${LABEL[rating].toLowerCase()}. Thank you.`)
      if (note) { setComment(""); setEditing(false) }
    }
    catch (e) { setError(message(e)) }
    finally { setBusy(false) }
  }
  if (current && !editing) return <div className="flex flex-wrap items-center justify-between gap-2 border-t border-rule pt-3 text-xs text-muted">
    <span className="flex items-center gap-1.5"><Face kind={current} className={`h-4 w-4 ${TONE[current]}`} />This session: <span className="text-ink">{LABEL[current]}</span></span>
    <button type="button" onClick={() => setEditing(true)} className="text-agentdeep underline-offset-4 hover:underline">Change or add a note</button>
  </div>
  return <div className="space-y-2 border-t border-rule pt-3">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <span className="text-sm text-ink">How is PharmAgentics working for you this session?</span>
      <div role="radiogroup" aria-label="Session rating" className="flex gap-1.5">
        {RATINGS.map(r => <button key={r} type="button" role="radio" aria-checked={current === r} disabled={busy} onClick={() => void send(r)}
          className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium ring-1 transition disabled:opacity-60 ${current === r ? `${BG[r]} ${TONE[r]} ring-current` : "text-ink ring-rule hover:bg-paper"}`}>
          <Face kind={r} className={`h-4 w-4 ${current === r ? "" : TONE[r]}`} />{LABEL[r]}</button>)}
      </div>
    </div>
    {current && <div className="flex flex-col gap-2 sm:flex-row sm:items-start">
      <label className="sr-only" htmlFor={`pulse-note-${refId}`}>{current === "good" ? "What is working?" : "What happened?"}</label>
      <textarea id={`pulse-note-${refId}`} value={comment} onChange={e => setComment(e.target.value)} maxLength={300} rows={2}
        placeholder={current === "good" ? "What is working? (optional)" : "What happened? (optional)"} className="min-w-0 flex-1 rounded-xl border border-rule bg-paper p-2.5 text-sm" />
      <div className="flex gap-2">
        <button type="button" disabled={busy || !comment.trim()} onClick={() => void send(current, comment)} className="rounded-lg px-3 py-2 text-xs font-semibold text-agentdeep border border-rule hover:bg-paper disabled:text-muted disabled:opacity-60">Send note</button>
        <button type="button" onClick={() => setEditing(false)} className="rounded-lg px-3 py-2 text-xs text-muted hover:text-ink">Done</button>
      </div>
    </div>}
    {error && <p role="alert" className="text-xs text-amber">{error}</p>}
  </div>
}

// --- the questionnaire ----------------------------------------------------------------------------

function Question({ item, scale, value, onChange }: { item: QItem; scale: string[]; value: unknown; onChange: (v: number | string | string[] | undefined) => void }) {
  const legend = <legend className="text-sm font-medium leading-snug">{item.text}</legend>
  const chip = (on: boolean) => `rounded-lg px-2 py-2 text-xs font-medium ring-1 transition ${on ? "bg-navy text-onaccent ring-navy" : "text-ink ring-rule hover:bg-paper"}`
  if (item.type === "agree5") return <fieldset className="space-y-2">{legend}
    <div role="radiogroup" aria-label={item.text} className="grid grid-cols-5 gap-1.5">
      {[1, 2, 3, 4, 5].map(n => <button key={n} type="button" role="radio" aria-checked={value === n} title={scale[n - 1]} onClick={() => onChange(value === n ? undefined : n)} className={chip(value === n)}>{n}</button>)}
    </div>
    <div className="flex justify-between text-[11px] text-muted"><span>{scale[0]}</span><span>{scale[4]}</span></div></fieldset>
  if (item.type === "nps") return <fieldset className="space-y-2">{legend}
    <div role="radiogroup" aria-label={item.text} className="grid grid-cols-11 gap-1">
      {Array.from({ length: 11 }, (_, n) => <button key={n} type="button" role="radio" aria-checked={value === n} onClick={() => onChange(value === n ? undefined : n)} className={chip(value === n)}>{n}</button>)}
    </div>
    <div className="flex justify-between text-[11px] text-muted"><span>{item.low}</span><span>{item.high}</span></div></fieldset>
  if (item.type === "choice") return <fieldset className="space-y-1.5">{legend}
    {item.options?.map(o => <label key={o.value} className="flex items-center gap-2 text-sm"><input type="radio" name={item.id} checked={value === o.value} onChange={() => onChange(o.value)} />{o.label}</label>)}
    {value !== undefined && <button type="button" onClick={() => onChange(undefined)} className="text-[11px] text-muted hover:underline">Clear</button>}</fieldset>
  if (item.type === "multi") {
    const picked = Array.isArray(value) ? value as string[] : []
    return <fieldset className="space-y-1.5">{legend}
      {item.options?.map(o => <label key={o.value} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={picked.includes(o.value)}
        onChange={() => onChange(picked.includes(o.value) ? picked.filter(v => v !== o.value) : [...picked, o.value])} />{o.label}</label>)}</fieldset>
  }
  const text = typeof value === "string" ? value : ""
  return <fieldset className="space-y-1.5">{legend}
    <textarea value={text} maxLength={item.max ?? 1000} rows={3} onChange={e => onChange(e.target.value)} aria-label={item.text} className="w-full rounded-xl border border-rule bg-paper p-2.5 text-sm" />
    <div className="text-right text-[11px] text-muted">{text.length}/{item.max ?? 1000}</div></fieldset>
}

const filled = (v: unknown) => v !== undefined && v !== "" && !(Array.isArray(v) && v.length === 0)

function SurveyModal({ onClose, onSubmitted }: { onClose: () => void; onSubmitted: () => void }) {
  const [q, setQ] = useState<Questionnaire | null>(null)
  const [answers, setAnswers] = useState<Answers>({})
  const [loadError, setLoadError] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)
  const [updating, setUpdating] = useState(false)

  const load = useCallback(() => {
    setLoadError(null); setQ(null)
    Promise.all([getQuestionnaire(), getMySurvey()]).then(([quest, mine]) => {
      const ids = new Map(quest.sections.flatMap(s => s.items).map((i): [string, QItem] => [i.id, i]))
      const prefill: Answers = {}   // earlier answers to questions that still exist, so an update starts from them
      for (const [id, v] of Object.entries(mine.answers)) {
        const item = ids.get(id)
        if (item && (typeof v === "number" || typeof v === "string" || Array.isArray(v))) prefill[id] = v as number | string | string[]
      }
      setQ(quest); setAnswers(prefill); setUpdating(Boolean(mine.submitted_at))
    }).catch(e => setLoadError(message(e)))
  }, [])
  useEffect(load, [load])
  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose() }
    document.addEventListener("keydown", esc)
    return () => document.removeEventListener("keydown", esc)
  }, [onClose])

  const set = (id: string, v: number | string | string[] | undefined) => setAnswers(a => { const n = { ...a }; if (filled(v)) n[id] = v as number | string | string[]; else delete n[id]; return n })
  const count = Object.values(answers).filter(filled).length
  const total = q ? q.sections.reduce((n, s) => n + s.items.length, 0) : 0
  const submit = async () => {
    if (!q) return
    setBusy(true); setError(null)
    try { await sendSurvey(q.version, answers); setDone(true); onSubmitted(); toast.success("Questionnaire saved. Thank you.") }
    catch (e) { setError(message(e)) }
    finally { setBusy(false) }
  }

  return <div className="fixed inset-0 z-50 flex justify-center overflow-y-auto overscroll-contain bg-black/60 px-3 py-6 backdrop-blur-sm">
    <div role="dialog" aria-modal="true" aria-labelledby="survey-title" className="h-fit w-full max-w-2xl rounded-xl bg-sheet shadow-xl border border-rule pa-rise">
      <div className="flex items-start justify-between gap-3 border-b border-rule px-6 py-4">
        <div><h2 id="survey-title" className="text-lg font-semibold">{q?.title ?? "Platform questionnaire"}</h2>{q && <p className="mt-1 text-sm text-muted">{q.intro}</p>}</div>
        <button type="button" onClick={onClose} aria-label="Close questionnaire" className="rounded-lg px-2 py-1 text-lg leading-none text-muted hover:bg-paper">×</button>
      </div>
      {loadError && <div role="alert" className="m-6 rounded-xl bg-amberbg p-4 text-sm text-amber">{loadError}<button type="button" onClick={load} className="mt-2 block underline">Try again</button></div>}
      {!q && !loadError && <p role="status" className="px-6 py-8 text-sm text-muted">Loading the questionnaire…</p>}
      {q && done && <div className="px-6 py-10 text-center"><p className="text-lg font-semibold">Thank you.</p>
        <p className="mt-1 text-sm text-muted">Your answers are saved. You can reopen the questionnaire from the sidebar or your account menu to change them.</p>
        <button type="button" onClick={onClose} className="mt-5 rounded-xl bg-navy px-5 py-2.5 text-sm font-semibold text-onaccent hover:bg-navyhover">Close</button></div>}
      {q && !done && <>
        <div className="space-y-7 px-6 py-5">
          {updating && <p className="rounded-xl bg-agentbg px-3 py-2 text-xs text-agentdeep">You answered this before. Your earlier answers are filled in; change anything and send again to replace them.</p>}
          {q.sections.map(section => <section key={section.id} className="space-y-5">
            <h3 className="border-b border-rule pb-1.5 font-sans text-[11px] font-semibold uppercase tracking-[0.05em] text-muted">{section.title}</h3>
            {section.items.map(item => <Question key={item.id} item={item} scale={q.scale.agree5} value={answers[item.id]} onChange={v => set(item.id, v)} />)}
          </section>)}
        </div>
        <div className="sticky bottom-0 flex flex-wrap items-center justify-between gap-3 rounded-b-2xl border-t border-rule bg-sheet px-6 py-3">
          <span className="text-xs text-muted">{count} of {total} answered. Every question is optional.</span>
          <span className="flex items-center gap-3">
            {error && <span role="alert" className="max-w-[18rem] text-xs text-amber">{error}{error.includes("changed") && <button type="button" onClick={load} className="ml-1 underline">Reload</button>}</span>}
            <button type="button" disabled={busy || count === 0} onClick={() => void submit()} className="rounded-xl bg-navy px-5 py-2.5 text-sm font-semibold text-onaccent hover:bg-navyhover disabled:bg-rule disabled:text-muted">{busy ? "Sending…" : updating ? "Send updated answers" : "Send"}</button>
          </span>
        </div>
      </>}
    </div>
  </div>
}
