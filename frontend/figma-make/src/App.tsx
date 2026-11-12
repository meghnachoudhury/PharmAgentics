import { useEffect, useMemo, useState, type ReactNode } from "react"
import { BrandMark, Icon } from "./agent/primitives"
import {
  getContext, getBriefing, getMe, getTriage, listPublished, markInsight, openBrief, reviewBrief, NotSignedIn,
  getAgentStatus, submitAgentJob, waitAgentJob, agentPlan, agentBrief,
  type AgentStatus, type AgentJob,
  type BriefingResult, type Claim, type Evidence, type LaneRole, type LeadershipBrief, type Me, type PublishedBrief, type ReleaseContext,
  type Stage, type TriageDecision, type TriagePlan, type TriageRecord,
} from "./agent/briefingApi"

// The backend implements a scripted WEEKLY BRIEF with role-based views (core-007). The server
// decides what each role receives; this UI only renders it. No mock data, no fake approvals.
function labelTerritory(id: string): string {
  return id.toLowerCase().split("_").map(s => s[0].toUpperCase() + s.slice(1)).join(" ").replace("Mid Atlantic", "Mid-Atlantic")
}
function labelWeek(iso: string): string {
  const [y,m,d] = iso.split("-").map(Number)
  return new Date(Date.UTC(y,m-1,d)).toLocaleDateString("en-US", {year:"numeric",month:"short",day:"numeric",timeZone:"UTC"})
}
function labelTime(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString("en-US", {month:"short",day:"numeric",hour:"numeric",minute:"2-digit"}) : "—"
}
function dataText(input: unknown): string {
  return input === null || input === undefined ? "—" : typeof input === "string" ? input : JSON.stringify(input, null, 2)
}
const message = (e: unknown) => e instanceof Error ? e.message : String(e)
const chip = "rounded px-2.5 py-1 text-[11px] font-medium"
const REVIEW_CHIP = {
  pending: [`${chip} bg-amberbg text-amber`, "Draft · Awaiting analyst review"],
  approved: [`${chip} bg-okbg text-ok`, "Approved · Visible to the Brand Director"],
  rejected: [`${chip} bg-warnbg text-warn`, "Rejected · Hidden from the Brand Director"],
} as const

function EvidenceDrawer({result, selectedId, onClose}: {result: BriefingResult, selectedId: string, onClose: () => void}) {
  const [id, setId] = useState(selectedId)
  useEffect(() => setId(selectedId), [selectedId])
  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if(e.key === "Escape") onClose() }
    document.addEventListener("keydown", esc)
    return () => document.removeEventListener("keydown", esc)
  }, [onClose])
  const claims = result.claims.filter(c=>c.evidence_id===id)
  const selected = result.evidence.find(e=>e.id===id)
  return <div className="fixed inset-0 z-40 flex justify-end">
    <button className="absolute inset-0 bg-ink/30" aria-label="Close evidence" onClick={onClose}/>
    <aside role="dialog" aria-modal="true" aria-label="Source evidence" className="relative z-10 flex h-full w-full max-w-xl flex-col bg-sheet shadow-2xl pa-slide">
      <div className="flex items-start justify-between border-b border-rule p-5">
        <div><div className="text-[11px] tracking-widest uppercase text-muted">Governed evidence</div><h2 className="mt-1 text-lg font-semibold">Source records</h2><p className="mt-1 text-xs text-muted">{result.evidence.length} evidence records · pinned version {result.data_version ?? "unavailable"}</p></div>
        <button onClick={onClose} aria-label="Close evidence panel" className="rounded-lg p-2 hover:bg-paper"><Icon name="close"/></button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="border-b border-rule p-3">
          {result.evidence.map(ev=><button key={ev.id} onClick={()=>setId(ev.id)} aria-current={id===ev.id} className={`flex w-full items-start gap-3 rounded-xl p-3 text-left text-sm ${id===ev.id?"bg-agentbg ring-1 ring-agent/20":"hover:bg-paper"}`}>
            <span className="font-mono text-xs text-agentdeep">{ev.id}</span><span className="min-w-0 flex-1">{ev.tool}<span className="block text-xs text-muted">{result.claims.filter(c=>c.evidence_id===ev.id).map(c=>c.value).join(", ") || "Context evidence"}</span></span>
          </button>)}
        </div>
        {selected && <div className="space-y-4 p-5">
          <div className="rounded-xl bg-paper p-4"><p className="text-xs text-muted">Claim values linked to this record</p><p className="mt-1 font-mono text-sm">{claims.length?claims.map(c=>c.value).join(" · "):"Context only"}</p></div>
          <div className="space-y-3 text-sm">
            <dl className="grid grid-cols-[90px_1fr] gap-3"><dt className="text-muted">Tool</dt><dd className="break-all font-mono text-xs">{selected.tool}</dd>
            <dt className="text-muted">Version</dt><dd className="break-all font-mono text-xs">{selected.data_version ?? "Not supplied"}</dd>
            <dt className="text-muted">Value</dt><dd className="break-all font-mono text-xs">{dataText(selected.result)}</dd></dl>
            {selected.query && <div><div className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">Source SQL</div><pre className="overflow-x-auto whitespace-pre-wrap break-all rounded-xl bg-paper p-3 font-mono text-xs leading-relaxed">{selected.query}</pre></div>}
            <div><div className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">Tool arguments</div><pre className="overflow-x-auto whitespace-pre-wrap rounded-xl bg-paper p-3 font-mono text-xs">{JSON.stringify(selected.params ?? {}, null, 2)}</pre></div>
          </div>
        </div>}
      </div>
    </aside>
  </div>
}

type NavItem = { key: string; label: string; icon: "briefings" | "evidence" | "layers"; active: boolean; onClick: () => void }

function Shell({me, role, title, subtitle, nav, children}: {me: Me, role?: LaneRole, title: string, subtitle: string, nav: NavItem[], children: ReactNode}) {
  const [mobileNav,setMobileNav] = useState(false)
  const side=<aside className="flex h-full w-full flex-col border-r border-rule bg-sheet/80">
    <div className="flex items-center gap-3 px-5 py-6"><BrandMark/><div><div className="text-[15px] font-semibold tracking-tight">PharmAgentics</div><div className="text-[11px] text-muted">Commercial Intelligence</div></div></div>
    <nav className="space-y-1 px-3" aria-label="Implemented features">{nav.map(n=><button key={n.key} aria-current={n.active} className={`flex w-full items-center gap-2 rounded-xl px-3 py-3 text-left text-sm font-medium ${n.active?"bg-paper ring-1 ring-rule":"hover:bg-paper/70"}`} onClick={()=>{n.onClick();setMobileNav(false)}}><Icon name={n.icon} className="text-agent"/>{n.label}</button>)}</nav>
    <div className="mt-auto border-t border-rule px-5 py-5 text-xs text-muted">
      <p className="font-semibold text-ink">{me.name || "Signed in"}</p>
      <p className="mt-1">{role ? `${role.label} (${role.persona}) · ${role.views.includes("analyst") ? "analyst view" : "leadership view"}` : "No Briefing role"}</p>
      {me.auth_mode==="dev" && <p className="mt-2 rounded bg-amberbg px-2 py-1 text-amber">Development sign-in (stand-in identity)</p>}
      <a className="mt-3 inline-block font-medium text-agentdeep hover:underline" href="/auth/logout">Sign out</a>
      <p className="mt-4">Synthetic data only. Scripted baseline; a leader sees a brief only after the Commercial Analyst approves it.</p>
    </div>
  </aside>
  return <div className="flex h-dvh overflow-hidden bg-paper text-ink">
    <div className="hidden w-[260px] shrink-0 md:block">{side}</div>
    {mobileNav && <div className="fixed inset-0 z-30 flex md:hidden"><button aria-label="Close navigation" className="absolute inset-0 bg-ink/30" onClick={()=>setMobileNav(false)}/><div className="relative w-[280px] max-w-[85vw] bg-paper">{side}</div></div>}
    <main className="flex min-w-0 flex-1 flex-col">
      <header className="flex items-center justify-between gap-3 border-b border-rule bg-sheet/80 px-5 py-3">
        <div className="flex min-w-0 items-center gap-3"><button className="rounded-lg p-1.5 md:hidden" aria-label="Open navigation" onClick={()=>setMobileNav(true)}><Icon name="menu"/></button><div className="min-w-0"><h1 className="truncate text-sm font-semibold">{title}</h1><p className="truncate text-[11px] text-muted">{subtitle}</p></div></div>
        <span className={`${chip} shrink-0 rounded-full bg-humanbg text-human`}>Synthetic data</span>
      </header>
      <section className="min-h-0 flex-1 overflow-y-auto">{children}</section>
    </main>
  </div>
}

function Centered({children}: {children: ReactNode}) {
  return <div className="grid h-dvh place-items-center bg-paper px-5 text-ink"><div className="max-w-md rounded-3xl bg-white p-7 text-center shadow-lg shadow-ink/5 ring-1 ring-rule"><div className="flex justify-center"><BrandMark size="lg"/></div>{children}</div></div>
}

function InsightButton({briefId, view}: {briefId: string, view: "analyst" | "leadership"}) {
  const [state,setState] = useState<"idle" | "saving" | "done" | string>("idle")
  useEffect(()=>setState("idle"),[briefId, view])
  if (state==="done") return <p role="status" className="text-xs text-ok">Recorded. Thank you.</p>
  return <div className="flex flex-wrap items-center gap-3">
    <button disabled={state==="saving"} onClick={async()=>{setState("saving");try{await markInsight(briefId, view);setState("done")}catch(e){setState(message(e))}}} className="rounded-xl bg-navy px-4 py-2.5 text-sm font-semibold text-white hover:bg-agentdeep disabled:bg-rule disabled:text-muted">I have what I need</button>
    {state!=="idle" && state!=="saving" && <span role="alert" className="text-xs text-amber">{state}</span>}
  </div>
}

function SummaryCard({brief, preview=false}: {brief: LeadershipBrief, preview?: boolean}) {
  return <article className="overflow-hidden rounded-2xl bg-sheet shadow-sm ring-1 ring-rule pa-rise">
    <div className="border-b border-rule px-6 py-5"><div className="flex flex-wrap items-center gap-2">
      <span className={`${chip} bg-humanbg text-human`}>{preview ? "Leadership preview" : "Executive summary"}</span>
      {brief.review_status==="approved" ? <span className={`${chip} bg-okbg text-ok`}>Approved by the Commercial Analyst · {labelTime(brief.reviewed_at)}</span> : <span className={REVIEW_CHIP[brief.review_status][0]}>{REVIEW_CHIP[brief.review_status][1]}</span>}
      {brief.abstained && <span className={`${chip} bg-amberbg text-amber`}>Unresolved findings</span>}
    </div><h2 className="mt-3 text-lg font-semibold">Weekly briefing · {labelTerritory(brief.territory_id)}</h2><p className="mt-1 text-sm text-muted">{labelWeek(brief.week_start)} · {brief.brand_id} · data version {brief.data_version ?? "unavailable"}</p></div>
    <div className="px-6 py-6"><pre className="whitespace-pre-wrap break-words font-sans text-[14px] leading-[1.85] text-ink">{brief.summary}</pre></div>
    <div className="border-t border-rule px-6 py-4 text-xs text-muted">Every figure comes from the approved analyst brief. Evidence and source queries stay with the Commercial Analyst.</div>
  </article>
}

function PublishedList({onOpen}: {onOpen: (id: string) => void}) {
  const [items,setItems] = useState<PublishedBrief[] | null>(null)
  const [error,setError] = useState<string | null>(null)
  useEffect(()=>{listPublished().then(setItems).catch(e=>setError(message(e)))},[])
  if (error) return <div role="alert" className="rounded-2xl bg-amberbg px-5 py-4 text-sm text-amber">{error}</div>
  if (!items) return <p className="text-sm text-muted">Loading approved briefings…</p>
  if (!items.length) return <div className="rounded-2xl bg-sheet px-5 py-6 text-sm text-muted ring-1 ring-rule">No approved briefings yet. A briefing appears here after the Commercial Analyst approves it.</div>
  return <ul className="space-y-2">{items.map(b=><li key={b.brief_id}><button onClick={()=>onOpen(b.brief_id)} className="flex w-full items-center justify-between gap-3 rounded-2xl bg-sheet px-5 py-4 text-left ring-1 ring-rule transition hover:ring-agent/40">
    <span><span className="block text-sm font-semibold">{labelTerritory(b.territory_id)} · week of {labelWeek(b.week_start)}</span><span className="mt-1 block text-xs text-muted">Approved {labelTime(b.reviewed_at)}{b.abstained ? " · unresolved findings" : ""}</span></span>
    <Icon name="chevronRight" className="h-4 w-4 text-muted"/></button></li>)}</ul>
}

function ReviewPanel({result, onChange}: {result: BriefingResult, onChange: (r: BriefingResult) => void}) {
  const [reason,setReason] = useState("")
  const [rejecting,setRejecting] = useState(false)
  const [busy,setBusy] = useState(false)
  const [error,setError] = useState<string | null>(null)
  const decide = async (decision: "approved" | "rejected") => {
    setBusy(true); setError(null)
    try { onChange(await reviewBrief(result.brief_id, decision, reason)); setRejecting(false); setReason("") }
    catch(e) { setError(message(e)) } finally { setBusy(false) }
  }
  return <section className="border-t border-rule px-6 py-5">
    <h3 className="text-sm font-semibold">Your review</h3>
    <p className="mt-1 text-xs text-muted">{result.review_status==="pending" ? "The Brand Director sees this briefing only after you approve it." : `${result.review_status==="approved"?"Approved":"Rejected"} ${labelTime(result.reviewed_at)}${result.review_reason?` · “${result.review_reason}”`:""}. You can change your decision.`}</p>
    {rejecting ? <div className="mt-3 space-y-2">
      <label className="block text-xs font-medium text-muted" htmlFor="reject-reason">Reason for rejecting (required)</label>
      <textarea id="reject-reason" value={reason} onChange={e=>setReason(e.target.value)} maxLength={500} rows={2} className="w-full rounded-xl border border-rule bg-paper p-3 text-sm"/>
      <div className="flex gap-2"><button disabled={busy || !reason.trim()} onClick={()=>void decide("rejected")} className="rounded-xl bg-neg px-4 py-2.5 text-sm font-semibold text-white disabled:bg-rule disabled:text-muted">Reject briefing</button><button onClick={()=>setRejecting(false)} className="rounded-xl px-4 py-2.5 text-sm text-muted hover:bg-paper">Cancel</button></div>
    </div> : <div className="mt-3 flex flex-wrap gap-2">
      <button disabled={busy || result.review_status==="approved"} onClick={()=>void decide("approved")} className="rounded-xl bg-ok px-4 py-2.5 text-sm font-semibold text-white disabled:bg-rule disabled:text-muted">Approve for the Brand Director</button>
      <button disabled={busy || result.review_status==="rejected"} onClick={()=>setRejecting(true)} className="rounded-xl px-4 py-2.5 text-sm font-medium text-neg ring-1 ring-rule hover:bg-paper disabled:text-muted">Reject…</button>
    </div>}
    {error && <p role="alert" className="mt-2 text-xs text-amber">{error}</p>}
  </section>
}

// brief-002 US8: the code triage plan, reviewed by the analyst before stage 4 runs.
const QUESTIONS = [["decision","Decision"],["population","Population"],["granularity","Granularity"],["time","Time"]] as const

function TriageReview({plan, busy, onApprove}: {plan: TriagePlan, busy: boolean, onApprove: (d: TriageDecision) => void}) {
  const proposed = plan.stories.filter(c=>c.proposed==="investigate").map(c=>c.id)
  // Agent plans start from the manager's plan (A1); P1 can still restore what the manager dropped.
  const start = plan.engine==="agent" && plan.manager_order ? plan.manager_order : proposed
  const startOrder = [...start, ...proposed.filter(id=>!start.includes(id))]
  const [order,setOrder] = useState<string[]>(startOrder)
  const [kept,setKept] = useState<Set<string>>(new Set(start))
  useEffect(()=>{setOrder(startOrder);setKept(new Set(start))},[plan.plan_id, plan.manager_order?.join()])  // eslint-disable-line react-hooks/exhaustive-deps
  const byId = new Map(plan.stories.map(c=>[c.id,c]))
  const move = (id: string, by: -1 | 1) => setOrder(o => { const i=o.indexOf(id), j=i+by; if(j<0||j>=o.length) return o; const n=[...o]; [n[i],n[j]]=[n[j],n[i]]; return n })
  const toggle = (id: string) => setKept(k => { const n=new Set(k); if(n.has(id)) n.delete(id); else n.add(id); return n })
  const decision: TriageDecision = {plan_id: plan.plan_id, stories: order.filter(id=>kept.has(id))}
  const changed = decision.stories.join() !== start.join()
  const over = plan.stories.filter(c=>c.proposed==="over_cap")
  return <div className="space-y-5 pa-rise">
    <div className="rounded-2xl bg-sheet px-6 py-5 ring-1 ring-rule">
      <div className="flex flex-wrap items-center gap-2"><span className={`${chip} bg-humanbg text-human`}>Triage review · your decision</span><span className={`${chip} bg-paper text-muted ring-1 ring-rule`}>Proposed by code</span></div>
      <h2 className="mt-3 text-lg font-semibold">What should this brief investigate?</h2>
      <p className="mt-1 text-sm text-muted">Code screened every territory and proposes the stories below, ranked by impact. Keep, drop or reorder them; investigation runs only on what you approve, in your order.</p>
      <details className="mt-4 rounded-xl bg-paper p-4 text-sm"><summary className="cursor-pointer font-medium">What stages 1 to 3 found (data health, restatements, KPIs)</summary><pre className="mt-3 whitespace-pre-wrap break-words font-sans text-[13px] leading-relaxed text-ink">{plan.context}</pre></details>
      {plan.engine==="agent" && plan.state==="TRIAGE_REVIEW" && <div className={`mt-4 rounded-xl p-4 text-sm ${plan.flagged?"bg-amberbg text-amber":"bg-agentbg text-agentdeep"}`}>
        <p className="font-medium">{plan.flagged ? "The manager's plan is flagged for your review" : "The manager kept code's plan"}<span className="font-normal"> · agent on the owner's PC ({plan.model})</span></p>
        {plan.flags?.map((f,i)=><p key={i} className="mt-1">{f}</p>)}
        {plan.manager_note && <p className="mt-1 text-ink">Manager's note: {plan.manager_note}</p>}
      </div>}
    </div>
    {plan.state==="OUT_OF_SCOPE" ? <div className="rounded-2xl bg-amberbg px-6 py-5 text-sm text-amber ring-1 ring-amberline"><p className="font-medium">The data cannot answer this question as asked.</p><p className="mt-1">{plan.scope}</p><p className="mt-2 text-ink">The brief will state this and give the scripted brief for the week. No investigation runs.</p></div> :
    plan.state!=="TRIAGE_REVIEW" ? <div className="rounded-2xl bg-sheet px-6 py-5 text-sm ring-1 ring-rule">{plan.state==="CALENDAR" ? "Calendar week: lower volume is expected, so code opens no story." : "Routine week: code found no material change, so there is no story to triage."}</div> :
    <ol className="space-y-3">{order.map((id, i)=>{ const c=byId.get(id)!; const on=kept.has(id); return <li key={id} className={`rounded-2xl bg-white p-5 ring-1 transition ${on?"ring-rule shadow-sm":"opacity-60 ring-rule"}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0"><div className="text-[11px] uppercase tracking-widest text-muted">{on ? `Story ${decision.stories.indexOf(id)+1}` : "Left out"} · code rank {c.rank}</div><h3 className="mt-1 text-base font-semibold">{c.title}</h3></div>
        <div className="flex shrink-0 items-center gap-1">
          <button aria-label={`Move ${c.title} up`} disabled={i===0} onClick={()=>move(id,-1)} className="rounded-lg px-2 py-1 text-sm ring-1 ring-rule disabled:opacity-30">↑</button>
          <button aria-label={`Move ${c.title} down`} disabled={i===order.length-1} onClick={()=>move(id,1)} className="rounded-lg px-2 py-1 text-sm ring-1 ring-rule disabled:opacity-30">↓</button>
          <label className="ml-2 flex items-center gap-2 text-sm"><input type="checkbox" checked={on} onChange={()=>toggle(id)}/>Investigate</label>
        </div>
      </div>
      <p className="mt-3 text-sm leading-relaxed">{c.what_moved}</p>
      {c.manager && <p className="mt-2 rounded-lg bg-agentbg px-3 py-2 text-[13px] text-agentdeep"><span className="font-medium">Manager (agent):</span> {c.manager.keep ? `keeps it as story ${c.manager.position}` : `drops it${c.manager.why ? `: ${c.manager.why}` : ""}`}{c.manager.hypotheses.length ? ` · tests in this order: ${c.manager.hypotheses.join(", ")}` : ""}</p>}
      <dl className="mt-3 grid gap-x-4 gap-y-2 text-[13px] sm:grid-cols-[110px_1fr]">{QUESTIONS.map(([k,label])=><div key={k} className="contents"><dt className="font-medium text-muted">{label}</dt><dd className="leading-relaxed">{c[k]}</dd></div>)}</dl>
    </li>})}</ol>}
    {(over.length>0 || plan.dropped.length>0) && <div className="rounded-2xl bg-sheet/70 px-6 py-5 text-sm ring-1 ring-rule">
      <h3 className="font-semibold">Dropped by code</h3><p className="mt-1 text-xs text-muted">These follow the rules; they cannot be added back to this brief.</p>
      <ul className="mt-3 space-y-1.5">{over.map(c=><li key={c.id}><span className="font-medium">{c.title}</span> <span className="text-muted">· over the story cap of this brief</span></li>)}{plan.dropped.map(d=><li key={d.territory}><span className="font-medium">{d.territory}</span> <span className="text-muted">· {d.reason}</span></li>)}</ul>
    </div>}
    <div className="flex flex-wrap items-center gap-3">
      <button disabled={busy} onClick={()=>onApprove(decision)} className="rounded-xl bg-navy px-5 py-3 text-sm font-semibold text-white hover:bg-agentdeep disabled:bg-rule disabled:text-muted">{plan.state!=="TRIAGE_REVIEW" ? "Write the brief" : changed ? "Approve my changes and investigate" : "Approve plan and investigate"}</button>
      {changed && <span className="text-xs text-muted">Your changes are recorded as your calls in the brief's triage record.</span>}
    </div>
  </div>
}

// brief-002 US7: who did each of the seven stages (Briefing Architecture §6 states, §9 modes).
const ACTOR = {code:["Code","bg-paper text-ink ring-1 ring-rule"], agent:["Agent","bg-agentbg text-agentdeep"], llm:["LLM step","bg-amberbg text-amber"], human:["Person","bg-humanbg text-human"]} as const

function FlowPanel({flow, triage}: {flow: Stage[], triage?: TriageRecord | null}) {
  return <details className="rounded-2xl bg-sheet px-6 py-5 ring-1 ring-rule">
    <summary className="cursor-pointer text-sm font-semibold">How this brief was made</summary>
    <ol className="mt-4 space-y-3">{flow.map(s=><li key={s.stage} className="grid gap-1 sm:grid-cols-[28px_1fr]">
      <span className="font-mono text-xs text-muted">{s.stage}</span>
      <div><div className="flex flex-wrap items-center gap-2"><span className="text-sm font-medium">{s.name}</span>{s.states.map(st=><span key={st} className="rounded bg-paper px-1.5 py-0.5 font-mono text-[10px] text-muted ring-1 ring-rule">{st}</span>)}</div>
        <div className="mt-1 flex flex-wrap gap-1.5">{s.actors.length ? s.actors.map((a,i)=><span key={i} className={`${chip} ${ACTOR[a.kind][1]}`}>{ACTOR[a.kind][0]}: {a.name}</span>) : <span className="text-xs text-muted">Skipped</span>}</div>
        <p className="mt-1 text-xs text-muted">{s.note}</p></div>
    </li>)}</ol>
    {triage && <div className="mt-5 border-t border-rule pt-4"><h4 className="text-xs font-semibold uppercase tracking-wider text-muted">Triage record</h4>
      <ul className="mt-2 space-y-1 text-xs">{triage.calls.map((c,i)=><li key={i} className="flex flex-wrap items-center gap-2"><span className={`${chip} ${ACTOR[c.layer][1]}`}>{({human:"You",agent:"Manager",code:"Code"} as const)[c.layer]}</span><span className="font-medium">{c.title}</span><span className="text-muted">{({investigated:"investigated as proposed",moved:c.layer==="agent"?"moved by the manager":"moved by you",dropped:c.layer==="agent"?`left out by the manager${c.why?`: ${c.why}`:""}`:"left out by you",restored:"put back by you after the manager dropped it",over_cap:"over the story cap",quiet:"within its normal range",withheld:"withheld at the feed gate"} as Record<string,string>)[c.outcome] ?? c.outcome}{c.position?` · story ${c.position}`:""}</span></li>)}</ul></div>}
  </details>
}

function AnalystBrief({result, onChange}: {result: BriefingResult, onChange: (r: BriefingResult) => void}) {
  const [evidenceId,setEvidenceId] = useState<string | null>(null)
  const [mode,setMode] = useState<"analyst" | "leadership">("analyst")
  const [preview,setPreview] = useState<LeadershipBrief | null>(null)
  const [previewError,setPreviewError] = useState<string | null>(null)
  useEffect(()=>{setMode("analyst");setPreview(null)},[result.brief_id])
  const showPreview = async () => {
    setMode("leadership"); setPreviewError(null)
    try { setPreview(await openBrief(result.brief_id, "leadership")) } catch(e) { setPreviewError(message(e)) }
  }
  const claimRows=useMemo(()=>{
    const byId=new Map(result.evidence.map(e=>[e.id,e]))
    return result.claims.map(cl=>({claim:cl,evidence:byId.get(cl.evidence_id)!}))
  },[result]) as {claim:Claim,evidence:Evidence}[]
  return <>
    <div role="tablist" aria-label="View" className="inline-flex rounded-xl bg-sheet p-1 ring-1 ring-rule">
      <button role="tab" aria-selected={mode==="analyst"} onClick={()=>setMode("analyst")} className={`rounded-lg px-3 py-1.5 text-xs font-medium ${mode==="analyst"?"bg-navy text-white":"text-muted"}`}>Analyst view</button>
      <button role="tab" aria-selected={mode==="leadership"} onClick={()=>void showPreview()} className={`rounded-lg px-3 py-1.5 text-xs font-medium ${mode==="leadership"?"bg-navy text-white":"text-muted"}`}>Leadership preview</button>
    </div>
    {mode==="leadership" ? (previewError ? <div role="alert" className="rounded-2xl bg-amberbg px-5 py-4 text-sm text-amber">{previewError}</div> : preview ? <SummaryCard brief={preview} preview/> : <p className="text-sm text-muted">Loading the leadership view…</p>) :
    <article className="overflow-hidden rounded-2xl bg-sheet shadow-sm ring-1 ring-rule">
      <div className="border-b border-rule px-6 py-5"><div className="flex flex-wrap items-center gap-2"><span className={`${chip} bg-agentbg text-agentdeep`}>{result.engine==="agent" ? `Agent · ${result.system.split(":").slice(1).join(":") || "local model"} · experimental` : "Scripted baseline · DuckDB"}</span><span className={REVIEW_CHIP[result.review_status][0]}>{REVIEW_CHIP[result.review_status][1]}</span>{result.abstained && <span className={`${chip} bg-amberbg text-amber`}>Unresolved findings</span>}</div><h2 className="mt-3 text-lg font-semibold">Weekly briefing · {labelTerritory(result.territory_id)}</h2><p className="mt-1 text-sm text-muted">{labelWeek(result.week_start)} · {result.brand_id}</p></div>
      <div className="px-6 py-6"><pre className="whitespace-pre-wrap break-words font-sans text-[14px] leading-[1.85] text-ink">{result.answer}</pre></div>
      <section className="border-t border-rule bg-paper/60 px-6 py-5"><div className="flex flex-wrap items-center justify-between gap-2"><div><h3 className="text-sm font-semibold">Evidence and numeric claims</h3><p className="mt-1 text-xs text-muted">Source queries and pinned data version supplied by the backend; no inferred chart data.</p></div><span className="rounded bg-sheet px-2 py-1 font-mono text-[11px] text-muted ring-1 ring-rule">{result.data_version??"Version unavailable"}</span></div>
      {claimRows.length > 0 ? <div className="mt-4 flex flex-wrap gap-2">{claimRows.map(({claim,evidence},idx)=><button className="flex items-center gap-2 rounded-lg bg-sheet px-3 py-2 text-xs ring-1 ring-rule transition hover:ring-agent/40" key={`${claim.evidence_id}-${idx}`} onClick={()=>setEvidenceId(evidence.id)}><span className="font-mono text-ink">{claim.value}</span><span className="text-agentdeep">{claim.evidence_id}</span><Icon name="chevronRight" className="h-3 w-3"/></button>)}</div> : <p className="mt-4 text-xs text-muted">The backend did not return numeric claims for this result.</p>}
      {result.evidence.length>0 && <button className="mt-4 flex items-center gap-2 text-xs font-medium text-agentdeep underline-offset-4 hover:underline" onClick={()=>setEvidenceId(result.evidence[0].id)}><Icon name="evidence"/>Browse all {result.evidence.length} evidence records</button>}
      </section>
      <ReviewPanel result={result} onChange={onChange}/>
    </article>}
    {mode==="analyst" && result.flow && <FlowPanel flow={result.flow} triage={result.triage}/>}
    <InsightButton briefId={result.brief_id} view={mode}/>
    {evidenceId && <EvidenceDrawer result={result} selectedId={evidenceId} onClose={()=>setEvidenceId(null)}/>}
  </>
}

function AnalystApp({me, role}: {me: Me, role: LaneRole}) {
  const [context,setContext] = useState<ReleaseContext | null>(null)
  const [contextError,setContextError] = useState<string | null>(null)
  const [loadingContext,setLoadingContext] = useState(true)
  const [brand,setBrand] = useState("")
  const [territory,setTerritory] = useState("")
  const [week,setWeek] = useState("")
  const [pending,setPending] = useState(false)
  const [result,setResult] = useState<BriefingResult | null>(null)
  const [runError,setRunError] = useState<string | null>(null)
  const [view,setView] = useState<"home" | "triage" | "result" | "approved">("home")
  const [requestScope,setRequestScope] = useState<{brand:string,territory:string,week:string} | null>(null)
  const [plan,setPlan] = useState<TriagePlan | null>(null)
  // Agent engine (core-007 FR-028): jobs run on the owner's PC; the app only queues them.
  const [engine,setEngine] = useState<"scripted" | "agent">("scripted")
  const [ask,setAsk] = useState("")
  const [agent,setAgent] = useState<AgentStatus | null>(null)
  const [triageJob,setTriageJob] = useState<string | null>(null)
  const [jobNote,setJobNote] = useState<string | null>(null)
  useEffect(()=>{
    let live = true
    const poll = () => getAgentStatus().then(s=>{ if(live) setAgent(s) }).catch(()=>{ if(live) setAgent(null) })
    poll(); const t = setInterval(poll, 15000)
    return ()=>{ live=false; clearInterval(t) }
  },[])
  const describeJob = (j: AgentJob) => setJobNote(j.status==="queued" ? "Queued for the agent host (the owner's PC)…" : j.status==="running" ? (j.kind==="triage" ? "The manager is reviewing code's plan on the agent host…" : "The agent team is investigating on the agent host (one to four minutes)…") : null)

  const refresh = async () => {
    setLoadingContext(true); setContextError(null)
    try {
      const c=await getContext()
      setContext(c)
      setBrand(b=>c.product_ids.includes(b)?b:c.product_ids[0])
      setTerritory(t=>c.territory_ids.includes(t)?t:c.territory_ids[0])
      setWeek(w=>c.available_weeks.includes(w)?w:c.latest_week)
    } catch(e) {setContext(null);setContextError(message(e))}
    finally {setLoadingContext(false)}
  }
  useEffect(()=>{void refresh()},[])

  const submit = async (event?: React.FormEvent) => {
    event?.preventDefault()
    if(pending || !context || !context.product_ids.includes(brand) || !context.territory_ids.includes(territory) || !context.available_weeks.includes(week)) return
    const selected={brand,territory,week}
    // Plan review is always on in UAT (brief-002 FR-019): stages 1 to 3 and the code triage first.
    setPending(true);setRunError(null);setResult(null);setPlan(null);setRequestScope(selected);setView("triage");setJobNote(null)
    try {
      if (engine==="agent") {
        const job = await submitAgentJob({kind:"triage", query: query(selected)})
        setTriageJob(job.id)
        const done = await waitAgentJob(job.id, describeJob)
        if (done.status==="failed") throw new Error(done.error ?? "The agent's triage failed.")
        setPlan(agentPlan(done))
      } else setPlan(await getTriage(query(selected)))
    } catch(e) {setRunError(message(e))}
    finally {setPending(false);setJobNote(null)}
  }
  const query = (s: {brand:string,territory:string,week:string}) => ({intent:"weekly_brief" as const,brand_id:s.brand,territory_id:s.territory,week_start:s.week,
    question: engine==="agent" && ask.trim().length>=3 ? ask.trim().slice(0,300) : "Generate the weekly brand-performance briefing."})
  const approvePlan = async (decision: TriageDecision) => {
    if(!requestScope) return
    setPending(true);setRunError(null);setResult(null);setView("result");setJobNote(null)
    try {
      if (plan?.engine==="agent" && triageJob) {
        const job = await submitAgentJob({kind:"brief", query: query(requestScope), triage_job: triageJob, decision})
        const done = await waitAgentJob(job.id, describeJob)
        if (done.status==="failed") throw new Error(done.error ?? "The agent's run failed.")
        setResult(agentBrief(done))
      } else {
        const response=await getBriefing({...query(requestScope)}, decision)
        setResult(response)
      }
    } catch(e) {setRunError(message(e))}
    finally {setPending(false);setJobNote(null)}
  }
  const openApproved = async (id: string) => {
    setRunError(null);setResult(null);setRequestScope(null);setView("result");setPending(true)
    try { setResult(await openBrief(id, "analyst")) } catch(e) { setRunError(message(e)) } finally { setPending(false) }
  }
  const selectable = !!context && !loadingContext && !pending
  const nav: NavItem[] = [
    {key:"brief",label:"Weekly briefing",icon:"briefings",active:view!=="approved",onClick:()=>setView("home")},
    {key:"approved",label:"Approved briefings",icon:"evidence",active:view==="approved",onClick:()=>setView("approved")},
  ]
  return <Shell me={me} role={role} title="Weekly Brand-Performance Briefing" subtitle="Analyst view · evidence-backed synthetic commercial analytics" nav={nav}>
    {view==="home" ? <div className="mx-auto flex max-w-3xl flex-col px-5 pb-10 pt-[7vh] md:pt-[10vh]">
      <div className="pa-rise flex flex-col items-center text-center"><BrandMark size="lg"/><h2 className="mt-6 text-[clamp(1.9rem,4vw,2.6rem)] font-semibold tracking-tight">What should we investigate?</h2><p className="mt-3 max-w-xl text-[15px] leading-relaxed text-muted">Generate a weekly brand-performance briefing from the governed DuckDB release, review its evidence, and approve it for the Brand Director.</p></div>
      <div className="mt-9 rounded-3xl bg-white p-5 shadow-lg shadow-ink/5 ring-1 ring-rule sm:p-7">
        {contextError && <div role="alert" className="mb-5 rounded-xl bg-amberbg p-4 text-sm text-amber"><strong>Backend unavailable.</strong> {contextError}<button className="mt-2 block underline" onClick={()=>void refresh()}>Retry connection</button></div>}
        {loadingContext && <p className="text-sm text-muted">Loading supported data context…</p>}
        <form onSubmit={submit} className="space-y-5">
          <div className="text-sm font-semibold">Weekly briefing</div>
          <div className="grid gap-4 sm:grid-cols-3">
            <label className="flex flex-col gap-2 text-xs font-medium text-muted">Brand
              <select aria-label="Brand" className="w-full min-w-0 rounded-xl border border-rule bg-paper px-3 py-3 text-sm text-ink" value={brand} onChange={e=>setBrand(e.target.value)} disabled={!selectable}>{context?.product_ids.map(id=><option key={id} value={id}>{id}</option>)}</select>
            </label>
            <label className="flex flex-col gap-2 text-xs font-medium text-muted">Territory
              <select aria-label="Territory" className="w-full min-w-0 rounded-xl border border-rule bg-paper px-3 py-3 text-sm text-ink" value={territory} onChange={e=>setTerritory(e.target.value)} disabled={!selectable}>{context?.territory_ids.map(id=><option key={id} value={id}>{labelTerritory(id)}</option>)}</select>
            </label>
            <label className="flex flex-col gap-2 text-xs font-medium text-muted">Reporting week
              <select aria-label="Reporting week" className="w-full min-w-0 rounded-xl border border-rule bg-paper px-3 py-3 text-sm text-ink" value={week} onChange={e=>setWeek(e.target.value)} disabled={!selectable}>{[...(context?.available_weeks??[])].reverse().map(w=><option key={w} value={w}>{labelWeek(w)}</option>)}</select>
            </label>
          </div>
          <fieldset className="space-y-2"><legend className="text-xs font-medium text-muted">Engine</legend>
            <div className="grid gap-2 sm:grid-cols-2">
              <label className={`flex cursor-pointer items-start gap-3 rounded-xl p-3 text-sm ring-1 ${engine==="scripted"?"bg-paper ring-ink/20":"ring-rule"}`}><input type="radio" name="engine" checked={engine==="scripted"} onChange={()=>setEngine("scripted")} className="mt-1"/><span><span className="font-medium">Scripted</span><span className="block text-xs text-muted">Instant. Fixed order of checks, manager off.</span></span></label>
              <label className={`flex cursor-pointer items-start gap-3 rounded-xl p-3 text-sm ring-1 ${engine==="agent"?"bg-paper ring-ink/20":"ring-rule"} ${agent?.configured===false?"opacity-50":""}`}><input type="radio" name="engine" checked={engine==="agent"} disabled={agent?.configured===false} onChange={()=>setEngine("agent")} className="mt-1"/><span><span className="font-medium">Agent team</span> <span className={`${chip} ${agent?.online?"bg-okbg text-ok":"bg-warnbg text-warn"}`}>{agent?.online ? "host online" : "host offline"}</span><span className="block text-xs text-muted">Manager, Data Forensics and Driver Investigator on the owner's PC ({agent?.model ?? "local model"}). Minutes per step; experimental.{!agent?.online ? " Your request waits until the host is back." : ""}</span></span></label>
            </div>
          </fieldset>
          {engine==="agent" && <label className="flex flex-col gap-2 text-xs font-medium text-muted">Your question (optional)
            <textarea value={ask} onChange={e=>setAsk(e.target.value)} maxLength={300} rows={2} placeholder="For example: Why did Pacific drop, and is anything else going on?" className="w-full rounded-xl border border-rule bg-paper px-3 py-3 text-sm text-ink"/>
          </label>}
          <button type="submit" disabled={!selectable} className="flex w-full items-center justify-center gap-2 rounded-xl bg-navy px-4 py-3.5 text-sm font-semibold text-white transition hover:bg-agentdeep disabled:cursor-not-allowed disabled:bg-rule disabled:text-muted"><Icon name="send"/>Generate weekly briefing</button>
        </form>
      </div>
      <div className="mt-6 rounded-xl border border-rule bg-sheet/65 p-4 text-sm text-muted"><p className="font-medium text-ink">Implemented functionality</p><p className="mt-1 leading-relaxed">This is the deterministic Briefing baseline (the manager-off version of the agent). Code checks the data and screens every territory, then you review its triage plan: keep, drop or reorder the stories before they are investigated. You then review the brief; only briefings you approve reach the Brand Director, as an executive summary without evidence. Each brief shows how it was made, stage by stage. The agent team (manager, Data Forensics, Driver Investigator) runs locally and is not in this app yet; free-form questions, Forecast explanations and charts are not implemented here.</p></div>
    </div> : view==="approved" ? <div className="mx-auto max-w-3xl space-y-5 px-5 py-7"><h2 className="text-lg font-semibold">Approved briefings</h2><p className="text-sm text-muted">What the Brand Director can open, on the current data release.</p><PublishedList onOpen={id=>void openApproved(id)}/></div>
    : <div className="mx-auto max-w-3xl space-y-5 px-5 py-7">
      <button className="flex items-center gap-2 text-sm text-agentdeep hover:underline" onClick={()=>setView("home")}><Icon name="back"/>Change scope</button>
      {requestScope && <div className="flex justify-end"><div className="max-w-[90%] rounded-2xl rounded-br-md bg-navy px-5 py-3 text-sm leading-relaxed text-white">Generate the weekly briefing for {requestScope.brand}, {labelTerritory(requestScope.territory)}, week of {labelWeek(requestScope.week)}.</div></div>}
      {pending && <div role="status" className="rounded-2xl bg-sheet px-5 py-4 text-sm text-muted ring-1 ring-rule">{jobNote ?? (view==="triage" ? "Checking the data and screening every territory (stages 1 to 3, code triage)…" : "Investigating the stories you approved (scripted checks against DuckDB)…")}</div>}
      {runError && <div role="alert" className="rounded-2xl bg-amberbg px-5 py-4 text-sm text-amber"><strong>{view==="triage" ? "The triage plan could not be built." : "Briefing could not be generated."}</strong><p className="mt-2">{runError}</p><p className="mt-2">No mock result was substituted.</p>{view==="result" && plan && <button className="mt-2 underline" onClick={()=>{setRunError(null);setView("triage")}}>Back to the triage plan</button>}</div>}
      {view==="triage" && plan && !pending && <TriageReview plan={plan} busy={pending} onApprove={d=>void approvePlan(d)}/>}
      {view==="result" && result && <AnalystBrief result={result} onChange={setResult}/>}
    </div>}
  </Shell>
}

function LeaderApp({me, role}: {me: Me, role: LaneRole}) {
  const [brief,setBrief] = useState<LeadershipBrief | null>(null)
  const [error,setError] = useState<string | null>(null)
  const [loading,setLoading] = useState(false)
  const open = async (id: string) => {
    setLoading(true); setError(null)
    try { setBrief(await openBrief(id, "leadership")) } catch(e) { setError(message(e)) } finally { setLoading(false) }
  }
  const nav: NavItem[] = [{key:"approved",label:"Approved briefings",icon:"briefings",active:true,onClick:()=>{setBrief(null);setError(null)}}]
  return <Shell me={me} role={role} title="Weekly Brand-Performance Briefing" subtitle="Leadership view · executive summaries approved by the Commercial Analyst" nav={nav}>
    <div className="mx-auto max-w-3xl space-y-5 px-5 py-7">
      {brief || loading || error ? <>
        <button className="flex items-center gap-2 text-sm text-agentdeep hover:underline" onClick={()=>{setBrief(null);setError(null)}}><Icon name="back"/>All approved briefings</button>
        {loading && <p role="status" className="text-sm text-muted">Opening the briefing…</p>}
        {error && <div role="alert" className="rounded-2xl bg-amberbg px-5 py-4 text-sm text-amber">{error}</div>}
        {brief && <><SummaryCard brief={brief}/><InsightButton briefId={brief.brief_id} view="leadership"/></>}
      </> : <><h2 className="text-lg font-semibold">Approved briefings</h2><p className="text-sm text-muted">Executive summaries the Commercial Analyst has reviewed and approved.</p><PublishedList onOpen={id=>void open(id)}/></>}
    </div>
  </Shell>
}

export default function App() {
  const [me,setMe] = useState<Me | null>(null)
  const [error,setError] = useState<string | null>(null)
  useEffect(()=>{
    getMe().then(setMe).catch(e=>{ if (e instanceof NotSignedIn) window.location.assign("/auth/login"); else setError(message(e)) })
  },[])
  if (error) return <Centered><h1 className="mt-5 text-lg font-semibold">Cannot reach PharmAgentics</h1><p className="mt-2 text-sm text-muted">{error}</p></Centered>
  if (!me) return <Centered><p className="mt-5 text-sm text-muted">Checking your sign-in…</p></Centered>
  const briefing = me.lanes.briefing
  if (!briefing) {
    const forecast = me.lanes.forecast
    return <Centered>
      <h1 className="mt-5 text-lg font-semibold">{forecast ? "The Forecast view is not available yet" : "No access"}</h1>
      <p className="mt-2 text-sm text-muted">{forecast ? `You are signed in as ${forecast.label} (${forecast.persona}). The Forecast-Explanation lane has not published its view in this app yet.` : "Your account has no PharmAgentics role. Ask the project owner to assign one."}</p>
      <a className="mt-5 inline-block text-sm font-medium text-agentdeep hover:underline" href="/auth/logout">Sign out</a>
    </Centered>
  }
  return briefing.actions.includes("run") ? <AnalystApp me={me} role={briefing}/> : <LeaderApp me={me} role={briefing}/>
}
