import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react"
import { Toaster, toast } from "sonner"
import { BrandMark, Icon, type IconName } from "./agent/primitives"
import { AnswerFeedback, FeedbackProvider, ShareFeedbackLink, useFeedbackActions } from "./Feedback"
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuRadioGroup, DropdownMenuRadioItem,
  DropdownMenuSeparator, DropdownMenuTrigger,
} from "./components/ui/dropdown-menu"
import {
  getContext, getBriefing, getMe, getTriage, listPublished, markInsight, openBrief, reviewBrief, NotSignedIn,
  getAgentStatus, submitAgentJob, waitAgentJob, agentPlan, agentBrief, getClassification, setViewAs,
  type AgentStatus, type AgentJob, type Classification,
  type BriefingResult, type Claim, type Evidence, type LeadershipBrief, type Me, type PublishedBrief, type ReleaseContext,
  type Stage, type TriageDecision, type TriagePlan, type TriageRecord,
} from "./agent/briefingApi"
import {
  createForecast, forecastCases, forecastContext, listForecasts, openForecast, reviewForecast, submitForecast,
  type ForecastCase, type ForecastContext, type ForecastRun, type ForecastSummary,
} from "./agent/forecastApi"

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
const chip = "rounded px-2 py-0.5 text-[11px] font-medium"
// One vocabulary for every screen: the primary action, a secondary action, a field, its label, a panel.
const BTN = "inline-flex items-center justify-center gap-2 rounded-lg bg-navy px-4 py-2 text-sm font-medium text-onaccent shadow-sm shadow-black/30 transition-[background-color,transform] duration-150 hover:bg-navyhover active:scale-[0.98] disabled:cursor-not-allowed disabled:bg-rule disabled:text-muted"
const BTN2 = "inline-flex items-center justify-center gap-2 rounded-lg border border-rule px-4 py-2 text-sm font-medium text-ink transition-[background-color,transform] duration-150 hover:bg-paper active:scale-[0.98] disabled:cursor-not-allowed disabled:text-muted"
const FIELD = "w-full min-w-0 rounded-lg border border-rule bg-paper px-3 py-2.5 text-sm text-ink disabled:opacity-60"
const LABEL = "flex flex-col gap-1.5 text-xs font-medium text-muted"
const PANEL = "rounded-xl border border-rule bg-sheet"
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
    <button className="absolute inset-0 bg-black/60" aria-label="Close evidence" onClick={onClose}/>
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

// Accounts show the role, not the test account's name: "UAT …" names and persona codes (P1, CA) are ours, not the user's.
function roleLabel(me: Me): string {
  const labels = [me.lanes.briefing?.label, me.lanes.forecast?.label].filter((l): l is string => !!l)
  return [...new Set(labels)].join(" · ") || "No role"
}
const LANES = [["briefing","Weekly briefing"],["forecast","Forecast explanation"]] as const

// The test login switches between the analyst roles (P1, CA) and the leadership roles (P3, BM) of both lanes.
// The page reloads after a switch: which app and which Forecast view to show are decided once, from /api/me.
function ViewAsSwitch({me}: {me: Me}) {
  const [busy,setBusy] = useState(false)
  const change = async (view: string) => {
    if (busy || view === me.view_as || (view !== "analyst" && view !== "leadership")) return
    setBusy(true)
    try { await setViewAs(view); window.location.reload() }
    catch (e) { toast.error(message(e)); setBusy(false) }
  }
  return <>
    <DropdownMenuSeparator/>
    <DropdownMenuLabel className="text-[11px] font-semibold uppercase tracking-[0.05em] text-muted">Test view</DropdownMenuLabel>
    <DropdownMenuRadioGroup value={me.view_as ?? "analyst"} onValueChange={v=>void change(v)}>
      <DropdownMenuRadioItem value="analyst" disabled={busy}>Analyst</DropdownMenuRadioItem>
      <DropdownMenuRadioItem value="leadership" disabled={busy}>Leadership</DropdownMenuRadioItem>
    </DropdownMenuRadioGroup>
  </>
}

function AccountMenu({me}: {me: Me}) {
  const {openSurvey, signOut, surveyDone} = useFeedbackActions()
  const role = roleLabel(me)
  return <DropdownMenu>
    <DropdownMenuTrigger aria-label={`Account: ${me.tester ? "test view, " : ""}${role}`} className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm text-ink outline-none transition hover:bg-paper">
      {me.tester && <span className="hidden text-xs text-muted sm:inline">Test view ·</span>}
      <Icon name="user" className="h-5 w-5 text-muted sm:hidden"/><span className="hidden max-w-[240px] truncate sm:inline">{role}</span>
      <svg viewBox="0 0 24 24" className="h-4 w-4 shrink-0 text-muted" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="end" className="w-72">
      <DropdownMenuLabel><span className="block truncate text-sm font-medium">{role}</span><span className="block text-xs font-normal text-muted">{me.auth_mode==="dev" ? "Development sign-in" : "Signed in"}</span></DropdownMenuLabel>
      <div className="space-y-2 px-3 pb-2 pt-1">{LANES.map(([lane,label])=>{ const r = me.lanes[lane]; return <div key={lane} className="text-xs">
        <p className="font-medium text-ink">{label}</p>
        <p className="text-muted">{r ? `${r.label}${r.available ? "" : " · coming soon"}` : "No access"}</p>
      </div>})}</div>
      {me.tester && <ViewAsSwitch me={me}/>}
      <DropdownMenuSeparator/>
      <DropdownMenuItem onSelect={openSurvey}><span className="flex-1">Platform questionnaire</span><span className="text-[11px] text-muted">{surveyDone ? "Update" : "5 min"}</span></DropdownMenuItem>
      <DropdownMenuItem onSelect={signOut}>Sign out</DropdownMenuItem>
    </DropdownMenuContent>
  </DropdownMenu>
}

// Data classification of a tab or view (core-009): a quiet text label from classification.json, the way a
// document carries its marking. Only Sensitive, the highest level, takes a colour. No enforcement here.
let classificationCache: Promise<Classification | null> | null = null
function useClassification(): Classification | null {
  const [c,setC] = useState<Classification | null>(null)
  useEffect(()=>{
    classificationCache ??= getClassification().catch(()=>null)
    let live = true
    void classificationCache.then(v=>{ if (live) setC(v) })
    return ()=>{ live = false }
  },[])
  return c
}
function ClassLabel({tab}: {tab: string}) {
  const c = useClassification()
  const id = c?.tabs[tab]
  const level = c?.levels.find(l=>l.id===id)
  if (!level) return null
  return <span title={`${level.label}: ${level.description}`} className={`whitespace-nowrap font-sans text-[11px] font-medium uppercase tracking-[0.06em] ${level.id === "sensitive" ? "text-neg" : "text-muted"}`}>
    <span className="sr-only">Data classification: </span>{level.label}
  </span>
}

function formatNumber(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : value.toLocaleString("en-US", { maximumFractionDigits: 1 })
}

function forecastReviewLabel(status: string): string {
  if (status === "not_submitted") return "Draft — submit to Brand Manager"
  if (status === "pending_review") return "Awaiting Brand Manager approval"
  if (status === "approved") return "Approved"
  if (status === "returned") return "Returned — revise and resubmit"
  if (status === "rejected") return "Not approved"
  return status.replace(/_/g, " ")
}

function ForecastReport({run}: {run: ForecastRun}) {
  const report = run.report
  return <div className="space-y-4">
    <article className="rounded-xl border border-rule bg-sheet p-6">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 text-xs text-muted">
        <span>{forecastReviewLabel(run.review_status)}{report.investigator_mode ? ` · ${report.investigator_mode === "ollama" ? "Agent (local model)" : "Scripted"}` : ""} · written report coming soon</span>
        <ClassLabel tab={`forecast.view.${run.view}`}/>
      </div>
      {report.abstained && <p className={`${chip} mt-3 inline-block bg-amberbg text-amber`}>Attribution paused</p>}
      <h2 className="mt-3 text-2xl">{report.headline}</h2>
      <p className="mt-1.5 text-sm text-muted">{labelTerritory(report.territory_id)} · week ending {labelWeek(report.week_ending)} · {report.window_weeks}-week window</p>
      <dl className="mt-5 grid grid-cols-3 divide-x divide-rule border-y border-rule">{[["Forecast",report.forecast_trx],["Actual",report.actual_trx],["Variance",report.variance_trx]].map(([label,value])=><div key={String(label)} className="px-4 py-3 first:pl-0"><dt className="text-xs text-muted">{label} TRx</dt><dd className="mt-0.5 text-lg font-medium tabular-nums">{formatNumber(value as number | null)}</dd></div>)}</dl>
      {report.variance_pct !== null && report.variance_pct !== undefined && <p className="mt-3 text-sm text-muted tabular-nums">Variance {(report.variance_pct * 100).toFixed(1)}% · residual {formatNumber(report.residual_trx)} TRx · verification {report.verification?.verdict ?? "—"}</p>}
    </article>
    <section className="rounded-xl border border-rule bg-sheet p-6"><h3 className="text-sm font-semibold">Drivers</h3>{report.drivers.length ? <ul className="mt-2 divide-y divide-rule">{report.drivers.map(d=><li key={d.driver} className="flex flex-wrap items-baseline justify-between gap-2 py-2.5 text-sm"><span className="capitalize">{d.driver}</span><span className="tabular-nums text-muted"><span className="text-ink">{formatNumber(d.impact_trx)} TRx</span> · {d.confidence}</span></li>)}</ul> : <p className="mt-2 text-sm text-muted">No driver attribution is shown because the data-quality gate paused this run.</p>}</section>
    {!!report.caveats.length && <section className="rounded-xl border border-amberline bg-amberbg p-6"><h3 className="text-sm font-semibold text-amber">Caveats</h3><ul className="mt-2 list-disc space-y-1 pl-5 text-sm">{report.caveats.map(c=><li key={c}>{c}</li>)}</ul></section>}
    {!!report.what_to_check.length && <section className="rounded-xl border border-rule bg-sheet p-6"><h3 className="text-sm font-semibold">What to check next</h3><ul className="mt-2 divide-y divide-rule">{report.what_to_check.map(c=><li key={c.question} className="py-3 text-sm"><p className="font-medium">{c.question}</p><p className="mt-1 text-muted">{c.why}</p><p className="mt-1 text-xs text-muted">Owner: <span className="text-ink">{c.owner}</span></p></li>)}</ul></section>}
    {run.view === "analyst" && run.stages && <section className="rounded-xl border border-rule bg-sheet p-6"><h3 className="text-sm font-semibold">How this explanation was made</h3><ol className="mt-2 divide-y divide-rule">{run.stages.map(s=><li key={s.stage} className="flex items-baseline justify-between gap-3 py-2 text-sm"><span><span className="mr-2 tabular-nums text-muted">{s.stage}</span>{s.name}</span><span className="text-xs text-muted">{s.status}</span></li>)}</ol></section>}
  </div>
}

// Each workspace keeps its sub-pages (a new run, the approved list) as tabs inside the page, not in the sidebar.
// The third item of an option is its classification key (core-009); the current tab's label sits at the row's end.
function SubTabs<T extends string>({label, value, options, onChange}: {label: string, value: T, options: readonly (readonly [T, string, string?])[], onChange: (v: T) => void}) {
  const current = options.find(o => o[0] === value)
  const list = useRef<HTMLDivElement>(null)
  const [bar,setBar] = useState<{left: number, width: number} | null>(null)
  useLayoutEffect(()=>{  // the underline slides to the selected tab
    const el = list.current?.querySelector<HTMLElement>('[aria-selected="true"]')
    if (el) setBar({left: el.offsetLeft, width: el.offsetWidth})
  },[value, options.length])
  return <div className="flex items-end justify-between gap-4 border-b border-rule">
    <div ref={list} role="tablist" aria-label={label} className="relative -mb-px flex gap-6 overflow-x-auto">
      {options.map(([key, text]) => <button key={key} type="button" role="tab" aria-selected={value === key} onClick={() => onChange(key)}
        className={`whitespace-nowrap pb-3 pt-1 text-sm font-medium transition-colors duration-200 ${value === key ? "text-ink" : "text-muted hover:text-ink"}`}>{text}</button>)}
      {bar && <span aria-hidden="true" className="pa-tabbar absolute bottom-0 h-0.5 rounded-full bg-agent" style={{left: bar.left, width: bar.width}}/>}
    </div>
    {current?.[2] && <div className="hidden pb-3 sm:block"><ClassLabel tab={current[2]}/></div>}
  </div>
}

// Analyst view / Leadership preview: a small neutral switch; the open view's classification is on the report itself.
function ViewToggle({value, busy=false, onChange}: {value: "analyst" | "leadership", busy?: boolean, onChange: (v: "analyst" | "leadership") => void}) {
  return <div role="tablist" aria-label="View" aria-busy={busy} className="inline-flex rounded-lg border border-rule p-0.5">
    {(["analyst", "leadership"] as const).map(v => <button key={v} type="button" role="tab" aria-selected={value === v} disabled={busy || value === v} onClick={() => onChange(v)}
      className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${value === v ? "bg-paper text-ink" : "text-muted hover:text-ink"}`}>
      {v === "analyst" ? "Analyst view" : "Leadership preview"}</button>)}
  </div>
}

type ForecastSection = "workbench" | "approved"
function ForecastWorkspace({me, section, onSection}: {me: Me, section: ForecastSection, onSection: (s: ForecastSection) => void}) {
  const r = me.lanes.forecast
  const analyst = !!r?.actions.includes("run")
  const canPreview = analyst && !!r?.views.includes("leadership")
  const [cases,setCases] = useState<ForecastCase[]>([])
  const [runs,setRuns] = useState<ForecastSummary[]>([])
  const [selected,setSelected] = useState<ForecastRun | null>(null)
  const [context,setContext] = useState<ForecastContext | null>(null)
  const [territory,setTerritory] = useState("NATIONAL")
  const [week,setWeek] = useState("")
  const [windowWeeks,setWindowWeeks] = useState(1)
  const [loading,setLoading] = useState(true)
  const [busy,setBusy] = useState(false)
  const [error,setError] = useState<string | null>(null)
  const [note,setNote] = useState("")
  useEffect(()=>setSelected(null), [section])
  // Match the Briefing workspace: the analyst can always return to the list of
  // their own runs, while the approved view is a strictly filtered list.
  const refresh = async () => { setLoading(true); setError(null); try { const status = section === "approved" ? "approved" : analyst ? undefined : "pending_review"; const values = await Promise.all([listForecasts(status), analyst && section === "workbench" ? forecastCases() : Promise.resolve([]), analyst && section === "workbench" ? forecastContext() : Promise.resolve(null)]); setRuns(values[0]); setCases(values[1]); setContext(values[2]); if (values[2]) { setTerritory(t=>values[2]!.territory_ids.includes(t) ? t : "NATIONAL"); setWeek(w=>values[2]!.available_weeks.includes(w) ? w : values[2]!.latest_week) } } catch(e) { setError(message(e)) } finally { setLoading(false) } }
  useEffect(()=>{ void refresh() }, [analyst, section])
  const start = async (c: ForecastCase) => { setBusy(true); setError(null); try { setSelected(await createForecast(c.request)); await refresh() } catch(e) { setError(message(e)) } finally { setBusy(false) } }
  const startCustom = async (event: React.FormEvent) => { event.preventDefault(); if (!week) return; setBusy(true); setError(null); try { setSelected(await createForecast({territory_id: territory, week_start: week, window_weeks: windowWeeks})); await refresh() } catch(e) { setError(message(e)) } finally { setBusy(false) } }
  const open = async (id: string, view?: ForecastRun["view"]) => {
    setBusy(true)
    setError(null)
    try {
      setSelected(await openForecast(id, view))
    } catch (e) {
      setError(message(e))
    } finally {
      setBusy(false)
    }
  }
  const submit = async () => { if (!selected) return; setBusy(true); setError(null); try { setSelected(await submitForecast(selected.forecast_run_id)); await refresh() } catch(e) { setError(message(e)) } finally { setBusy(false) } }
  const decide = async (decision: "approved" | "rejected" | "returned") => { if (!selected) return; setBusy(true); setError(null); try { setSelected(await reviewForecast(selected.forecast_run_id, decision, note)); setNote(""); await refresh() } catch(e) { setError(message(e)) } finally { setBusy(false) } }
  return <div className="workspace-content space-y-6 py-8 sm:py-10 pa-rise">
    {!selected && <Greeting detail={context ? `Forecast versus actual, through ${labelWeek(context.latest_week)}.` : undefined}/>}
    <SubTabs label="Forecast explanation" value={section} onChange={onSection} options={[["workbench", analyst ? "New explanation" : "To review", analyst ? "forecast.new" : "forecast.review"], ["approved", "Approved explanations", "forecast.approved"]] as const}/>
    {error && <div role="alert" className="rounded-xl bg-amberbg px-5 py-4 text-sm text-amber">{error}</div>}
    {selected ? <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <button disabled={busy} className="flex items-center gap-1.5 text-sm text-agentdeep hover:underline" onClick={()=>setSelected(null)}><Icon name="back"/>All {section === "approved" ? "approved explanations" : "forecast runs"}</button>
        {canPreview && <ViewToggle value={selected.view} busy={busy} onChange={view => void open(selected.forecast_run_id, view)}/>}
      </div>
      <ForecastReport run={selected}/>
      <AnswerFeedback lane="forecast" refId={selected.forecast_run_id} view={selected.view}/>
      {analyst && selected.view === "analyst" && selected.review_status === "pending_review" && <p className="text-sm text-muted"><span className="text-ink">Submitted for Brand Manager approval.</span> It can no longer be edited; the Brand Manager can approve, return or reject it.</p>}
      {analyst && selected.view === "analyst" && section === "workbench" && (selected.review_status === "not_submitted" || selected.review_status === "returned") && <div className="flex justify-end"><button disabled={busy} onClick={()=>void submit()} className={BTN}>Submit to Brand Manager</button></div>}
      {!analyst && selected.review_status === "pending_review" && <section className={`${PANEL} p-5`}>
        <label className={LABEL}>Review note (needed to return or reject)<textarea value={note} onChange={e=>setNote(e.target.value)} className={`${FIELD} mt-0.5`} rows={3}/></label>
        <div className="mt-4 flex flex-wrap justify-end gap-2">
          <button disabled={busy || !note.trim()} onClick={()=>void decide("rejected")} className={BTN2}>Reject</button>
          <button disabled={busy || !note.trim()} onClick={()=>void decide("returned")} className={BTN2}>Return</button>
          <button disabled={busy} onClick={()=>void decide("approved")} className={BTN}>Approve</button>
        </div>
      </section>}
    </> : <>{analyst && section === "workbench" && <>
      <p className="text-sm text-muted">Forecast versus actual TRx for {context?.brand ?? "BXA"}, and the drivers behind the gap.</p>
      <form onSubmit={startCustom} className={`${PANEL} space-y-5 p-6`}>
        <div className="grid gap-4 sm:grid-cols-3">
          <label className={LABEL}>Territory<select value={territory} onChange={e=>setTerritory(e.target.value)} disabled={!context || busy} className={FIELD}>{context?.territory_ids.map(id=><option key={id} value={id}>{labelTerritory(id)}</option>)}</select></label>
          <label className={LABEL}>Reporting week<select value={week} onChange={e=>setWeek(e.target.value)} disabled={!context || busy} className={FIELD}>{[...(context?.available_weeks ?? [])].reverse().map(w=><option key={w} value={w}>{labelWeek(w)}</option>)}</select></label>
          <label className={LABEL}>Analysis window<select value={windowWeeks} onChange={e=>setWindowWeeks(Number(e.target.value))} disabled={busy} className={FIELD}><option value={1}>1 week</option><option value={4}>4 weeks</option><option value={13}>13 weeks</option></select></label>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-rule pt-4"><span className="text-xs text-muted">{context?.brand ?? "BXA Cardiovela"} · TRx</span><button type="submit" disabled={!context || !week || busy} className={BTN}>{busy ? "Generating…" : "Generate explanation"}</button></div>
      </form>
      {!!cases.length && <section><h3 className="text-sm font-semibold">Suggested investigations</h3><ul className={`${PANEL} pa-stagger mt-2 divide-y divide-rule`}>{cases.map(c=><li key={c.case_id}><button disabled={busy} onClick={()=>void start(c)} className="group flex w-full items-center justify-between gap-4 px-5 py-3.5 text-left transition-colors hover:bg-paper/60 disabled:opacity-60"><span className="min-w-0"><span className="block text-sm">{c.label}</span><span className="mt-0.5 block text-xs text-muted">{c.tag} · {labelTerritory(c.request.territory_id)} · {labelWeek(c.request.week_start)}</span></span><Icon name="chevronRight" className="h-4 w-4 shrink-0 text-muted transition-transform duration-200 group-hover:translate-x-0.5 group-hover:text-agent"/></button></li>)}</ul></section>}
    </>}
    <section><h3 className="text-sm font-semibold">{section === "approved" ? "Approved explanations" : analyst ? "Your forecast runs" : "Waiting for your review"}</h3>{loading ? <div className="mt-2"><ListSkeleton/></div> : runs.length ? <ul className={`${PANEL} pa-stagger mt-2 divide-y divide-rule`}>{runs.map(run=><li key={run.forecast_run_id}><button disabled={busy} onClick={()=>void open(run.forecast_run_id)} className="group flex w-full items-center justify-between gap-4 px-5 py-3.5 text-left transition-colors hover:bg-paper/60"><span className="min-w-0"><span className="block text-sm">{run.headline}</span><span className="mt-0.5 block text-xs text-muted tabular-nums">{labelTerritory(run.territory_id)} · variance {formatNumber(run.variance_trx)} TRx · {forecastReviewLabel(run.review_status)}</span></span><Icon name="chevronRight" className="h-4 w-4 shrink-0 text-muted transition-transform duration-200 group-hover:translate-x-0.5 group-hover:text-agent"/></button></li>)}</ul> : <p className="mt-2 text-sm text-muted">{section === "approved" ? "No approved explanations yet. They appear here once the Brand Manager approves one." : analyst ? "No forecast runs yet. Generate one above, or start from a suggested investigation." : "Nothing is waiting for your review."}</p>}</section></>}
  </div>
}

// The sidebar is a narrow rail of icons; a toggle in the header (or Ctrl+B) opens it to full width, and the page
// re-centres beside it. The choice is remembered in this browser. On phones the same toggle opens a slide-out menu.
// Every icon has an explicit size: a className without one lets the SVG grow to fill its row.
const OPEN_KEY = "pa_sidebar_open"
const readOpen = () => { try { return window.localStorage.getItem(OPEN_KEY) === "1" } catch { return false } }

function SideNav({me, expanded, forecast, onBriefing, onForecast, onAnyClick}: {me: Me, expanded: boolean, forecast: boolean, onBriefing?: () => void, onForecast: () => void, onAnyClick?: () => void}) {
  const row = (active: boolean) => `group flex w-full items-center gap-3 rounded-lg px-[10px] py-2.5 text-left text-sm transition-colors duration-150 ${active ? "bg-paper text-ink" : "text-muted hover:bg-paper/60 hover:text-ink"}`
  const label = (text: string) => <span className={expanded ? "truncate whitespace-nowrap pa-fade" : "sr-only"}>{text}</span>
  const item = (icon: IconName, text: string, active: boolean, go: () => void) =>
    <button aria-current={active ? "page" : undefined} title={expanded ? undefined : text} className={row(active)} onClick={()=>{go();onAnyClick?.()}}><Icon name={icon} className={`h-5 w-5 shrink-0 transition-colors ${active ? "text-agent" : "group-hover:text-agent"}`}/>{label(text)}</button>
  return <div className="flex h-full flex-col">
    <div className="flex h-16 items-center gap-3 px-[14px]">
      <BrandMark/>
      {expanded && <span className="pa-fade flex-1 truncate whitespace-nowrap font-serif text-[18px] font-medium">PharmAgentics</span>}
    </div>
    <nav className="mt-2 space-y-1 px-3" aria-label="Workspaces">
      {onBriefing && item("briefings", "Weekly briefing", !forecast, onBriefing)}
      {me.lanes.forecast?.available && item("trend", "Forecast explanation", forecast, onForecast)}
    </nav>
    <div className="mt-auto space-y-2 px-3 pb-4">
      {me.auth_mode==="dev" && expanded && <p className="rounded-lg bg-amberbg px-2.5 py-1 text-[11px] text-amber">Development sign-in</p>}
      <ShareFeedbackLink expanded={expanded} onOpen={onAnyClick}/>
    </div>
  </div>
}

function Shell({me, onBriefingHome, children, startInForecast=false}: {me: Me, onBriefingHome?: () => void, children: ReactNode, startInForecast?: boolean}) {
  const [mobileNav,setMobileNav] = useState(false)
  const [forecast,setForecast] = useState(startInForecast)
  const [forecastSection,setForecastSection] = useState<ForecastSection>("workbench")
  const [open,setOpen] = useState(readOpen)
  const toggle = () => setOpen(o => { try { window.localStorage.setItem(OPEN_KEY, o ? "0" : "1") } catch { /* a convenience only */ } return !o })
  const toggleNav = () => { if (window.matchMedia("(min-width: 768px)").matches) toggle(); else setMobileNav(true) }
  useEffect(()=>{
    const key = (e: KeyboardEvent) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "b") { e.preventDefault(); toggleNav() } }
    window.addEventListener("keydown", key)
    return () => window.removeEventListener("keydown", key)
  },[])
  const goBriefing = onBriefingHome ? () => { setForecast(false); onBriefingHome() } : undefined
  const goForecast = () => { setForecast(true); setForecastSection("workbench") }
  const leader = !me.lanes.briefing?.views.includes("analyst") && !me.lanes.forecast?.views.includes("analyst")
  // --rail is the width the sidebar occupies; .workspace-content uses it to centre on the whole page (0 on phones).
  return <FeedbackProvider where={forecast ? "forecast" : "briefing"}><div className={`flex h-dvh overflow-hidden text-ink max-md:[--rail:0px] ${open ? "[--rail:248px]" : "[--rail:64px]"}`}>
    <aside aria-label="Sidebar" className={`hidden shrink-0 overflow-hidden border-r border-rule bg-sheet transition-[width] duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] md:block ${open ? "w-[248px]" : "w-16"}`}>
      <SideNav me={me} expanded={open} forecast={forecast} onBriefing={goBriefing} onForecast={goForecast}/>
    </aside>
    {mobileNav && <div className="fixed inset-0 z-40 flex md:hidden"><button aria-label="Close navigation" className="pa-fade absolute inset-0 bg-black/60" onClick={()=>setMobileNav(false)}/>
      <div className="glass relative w-[280px] max-w-[85vw] overscroll-contain border-r border-rule pa-slide"><SideNav me={me} expanded forecast={forecast} onBriefing={goBriefing} onForecast={goForecast} onAnyClick={()=>setMobileNav(false)}/></div></div>}
    <main className="flex min-w-0 flex-1 flex-col">
      <header className="flex h-16 shrink-0 items-center justify-between gap-3 border-b border-rule px-4 sm:px-5">
        <div className="flex min-w-0 items-center gap-2">
          <button type="button" onClick={toggleNav} aria-expanded={open} aria-label={open ? "Collapse the sidebar" : "Expand the sidebar"} title={`${open ? "Collapse" : "Expand"} the sidebar (Ctrl+B)`}
            className="grid h-9 w-9 place-items-center rounded-lg text-muted transition-colors hover:bg-paper hover:text-ink"><Icon name="panel" className="h-5 w-5"/></button>
          <h1 key={forecast ? "f" : "b"} className="pa-fade truncate text-base sm:text-lg">{forecast ? "Forecast explanation" : "Weekly briefing"}</h1>
        </div>
        <AccountMenu me={me}/>
      </header>
      <section className="min-h-0 flex-1 overflow-y-auto"><div hidden={forecast}>{children}</div>{forecast && <ForecastWorkspace key={forecastSection} me={me} section={forecastSection} onSection={setForecastSection}/>}</section>
      <footer className="shrink-0 border-t border-rule px-5 py-2 text-center text-[11px] text-muted">PharmAgentics can make mistakes. Check important figures {leader ? "with the Commercial Analyst" : "against the evidence"}.</footer>
    </main>
    <Toaster theme="dark" position="bottom-right" toastOptions={{className: "glass !bg-transparent !text-ink !border !border-rule !font-sans !rounded-xl"}}/>
  </div></FeedbackProvider>
}

function Centered({children}: {children: ReactNode}) {
  return <div className="grid h-dvh place-items-center px-5 text-ink"><div className="max-w-md rounded-xl bg-sheet p-7 text-center border border-rule"><div className="flex justify-center"><BrandMark size="lg"/></div>{children}</div></div>
}

function InsightButton({briefId, view}: {briefId: string, view: "analyst" | "leadership"}) {
  const [state,setState] = useState<"idle" | "saving" | "done" | string>("idle")
  useEffect(()=>setState("idle"),[briefId, view])
  if (state==="done") return <p role="status" className="text-xs text-ok">Recorded. Thank you.</p>
  return <div className="flex flex-wrap items-center gap-3">
    <button disabled={state==="saving"} onClick={async()=>{setState("saving");try{await markInsight(briefId, view);setState("done")}catch(e){setState(message(e))}}} className={BTN2}>I have what I need</button>
    {state!=="idle" && state!=="saving" && <span role="alert" className="text-xs text-amber">{state}</span>}
  </div>
}

function SummaryCard({brief, preview=false}: {brief: LeadershipBrief, preview?: boolean}) {
  return <><article className={`${PANEL} overflow-hidden pa-rise`}>
    <div className="border-b border-rule px-6 py-5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 text-xs text-muted">
        <span>{preview ? "Leadership preview" : "Executive summary"}</span>
        <ClassLabel tab="briefing.view.leadership"/>
      </div>
      <h2 className="mt-2 text-2xl">{labelTerritory(brief.territory_id)}, week of {labelWeek(brief.week_start)}</h2>
      <p className="mt-1.5 text-sm text-muted">{brief.brand_id} · data version {brief.data_version ?? "unavailable"}</p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {brief.review_status==="approved" ? <span className={`${chip} inline-flex items-center gap-1 bg-okbg text-ok`}><Icon name="check" className="h-3.5 w-3.5"/>Approved by the Commercial Analyst · {labelTime(brief.reviewed_at)}</span> : <span className={REVIEW_CHIP[brief.review_status][0]}>{REVIEW_CHIP[brief.review_status][1]}</span>}
        {brief.abstained && <span className={`${chip} bg-amberbg text-amber`}>Unresolved findings</span>}
      </div>
    </div>
    <div className="px-6 py-6"><pre className="max-w-[68ch] whitespace-pre-wrap break-words font-serif text-[16px] leading-[1.7] text-ink">{brief.summary}</pre></div>
    <div className="border-t border-rule px-6 py-4 text-xs text-muted">Every figure comes from the approved analyst brief. Evidence and source queries stay with the Commercial Analyst.</div>
  </article>
  <AnswerFeedback lane="briefing" refId={brief.brief_id} view="leadership"/></>
}

// A short, warm start to each workspace, from the viewer's own clock.
function Greeting({detail}: {detail?: string}) {
  const h = new Date().getHours()
  const part = h < 5 ? "Working late" : h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening"
  return <div className="pa-fade mb-7"><h2 className="text-[1.75rem] leading-tight">{part}.</h2>{detail && <p className="mt-1 text-sm text-muted">{detail}</p>}</div>
}

// An agent job's real progress: the server reports queued, then running; the result arrives when it is done and
// has passed the traceability check. The clock is the real elapsed time; nothing here is simulated.
function JobProgress({kind, status, note}: {kind: "triage" | "brief", status: "queued" | "running", note: string | null}) {
  const [start] = useState(() => Date.now())
  const [now,setNow] = useState(() => Date.now())
  useEffect(()=>{ const t = setInterval(()=>setNow(Date.now()), 1000); return ()=>clearInterval(t) },[])
  const secs = Math.floor((now - start) / 1000)
  const steps = [
    ["queued", "Queued"],
    ["running", kind === "triage" ? "The manager is reviewing the plan" : "The agent team is investigating"],
    ["check", "Every number checked against its source, then shown to you"],
  ] as const
  const at = status === "queued" ? 0 : 1
  return <section role="status" aria-live="polite" className={`${PANEL} pa-fade p-6`}>
    <div className="flex items-baseline justify-between gap-3"><h3 className="text-sm font-semibold">{kind === "triage" ? "Preparing the plan" : "Writing the briefing"}</h3><span className="text-xs tabular-nums text-muted">{Math.floor(secs / 60)}:{String(secs % 60).padStart(2, "0")}</span></div>
    <ol className="mt-4 space-y-3">{steps.map(([id, text], i) => <li key={id} className={`flex items-center gap-3 text-sm transition-colors duration-300 ${i < at ? "text-muted" : i === at ? "text-ink" : "text-muted/60"}`}>
      <span aria-hidden="true" className="grid h-5 w-5 shrink-0 place-items-center">
        {i < at ? <svg viewBox="0 0 24 24" className="pa-draw h-4 w-4 text-agent" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>
          : i === at ? <span className="h-2 w-2 rounded-full bg-agent pa-pulse"/> : <span className="h-1.5 w-1.5 rounded-full bg-rule"/>}
      </span>{text}</li>)}</ol>
    {note && <p className="mt-4 text-xs text-muted">{note}</p>}
  </section>
}

function ListSkeleton({rows=3}: {rows?: number}) {
  return <div role="status" className={`${PANEL} divide-y divide-rule`}><span className="sr-only">Loading…</span>{Array.from({length: rows}, (_, i) => <div key={i} className="space-y-2 px-5 py-4"><div className="pa-skeleton h-3.5 w-1/2"/><div className="pa-skeleton h-3 w-1/3"/></div>)}</div>
}

function PublishedList({onOpen}: {onOpen: (id: string) => void}) {
  const [items,setItems] = useState<PublishedBrief[] | null>(null)
  const [error,setError] = useState<string | null>(null)
  useEffect(()=>{listPublished().then(setItems).catch(e=>setError(message(e)))},[])
  if (error) return <div role="alert" className="rounded-xl bg-amberbg px-5 py-4 text-sm text-amber">{error}</div>
  if (!items) return <ListSkeleton/>
  if (!items.length) return <p className="text-sm text-muted">No approved briefings yet. A briefing appears here once the Commercial Analyst approves it.</p>
  return <ul className={`${PANEL} pa-stagger divide-y divide-rule`}>{items.map(b=><li key={b.brief_id}><button onClick={()=>onOpen(b.brief_id)} className="group flex w-full items-center justify-between gap-4 px-5 py-3.5 text-left transition-colors hover:bg-paper/60">
    <span className="min-w-0"><span className="block text-sm">{labelTerritory(b.territory_id)}, week of {labelWeek(b.week_start)}</span><span className="mt-0.5 block text-xs text-muted">Approved {labelTime(b.reviewed_at)}{b.abstained ? " · unresolved findings" : ""}</span></span>
    <Icon name="chevronRight" className="h-4 w-4 shrink-0 text-muted transition-transform duration-200 group-hover:translate-x-0.5 group-hover:text-agent"/></button></li>)}</ul>
}

function ReviewPanel({result, onChange}: {result: BriefingResult, onChange: (r: BriefingResult) => void}) {
  const [reason,setReason] = useState("")
  const [rejecting,setRejecting] = useState(false)
  const [busy,setBusy] = useState(false)
  const [error,setError] = useState<string | null>(null)
  const decide = async (decision: "approved" | "rejected") => {
    setBusy(true); setError(null)
    try { onChange(await reviewBrief(result.brief_id, decision, reason)); setRejecting(false); setReason(""); toast.success(decision==="approved" ? "Approved. The Brand Director can now open it." : "Rejected. It stays hidden from the Brand Director.") }
    catch(e) { setError(message(e)) } finally { setBusy(false) }
  }
  return <section className="border-t border-rule px-6 py-5">
    <h3 className="text-sm font-semibold">Your review</h3>
    <p className="mt-1 text-xs text-muted">{result.review_status==="pending" ? "The Brand Director sees this briefing only after you approve it." : `${result.review_status==="approved"?"Approved":"Rejected"} ${labelTime(result.reviewed_at)}${result.review_reason?` · “${result.review_reason}”`:""}. You can change your decision.`}</p>
    {rejecting ? <div className="mt-3 space-y-2">
      <label className="block text-xs font-medium text-muted" htmlFor="reject-reason">Reason for rejecting (required)</label>
      <textarea id="reject-reason" value={reason} onChange={e=>setReason(e.target.value)} maxLength={500} rows={2} className={FIELD}/>
      <div className="flex justify-end gap-2"><button onClick={()=>setRejecting(false)} className={BTN2}>Cancel</button><button disabled={busy || !reason.trim()} onClick={()=>void decide("rejected")} className={`${BTN2} border-neg/50 text-neg hover:bg-neg/10`}>Reject briefing</button></div>
    </div> : <div className="mt-3 flex flex-wrap justify-end gap-2">
      <button disabled={busy || result.review_status==="rejected"} onClick={()=>setRejecting(true)} className={`${BTN2} text-neg`}>Reject…</button>
      <button disabled={busy || result.review_status==="approved"} onClick={()=>void decide("approved")} className={BTN}>Approve for the Brand Director</button>
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
    <div className="rounded-xl bg-sheet px-6 py-5 border border-rule">
      <div className="flex flex-wrap items-center gap-2"><span className={`${chip} bg-humanbg text-human`}>Triage review · your decision</span><span className={`${chip} bg-paper text-muted border border-rule`}>Proposed by code</span></div>
      <h2 className="mt-3 text-lg font-semibold">What should this brief investigate?</h2>
      <p className="mt-1 text-sm text-muted">Code screened every territory and proposes the stories below, ranked by impact. Keep, drop or reorder them; investigation runs only on what you approve, in your order.</p>
      <details className="mt-4 rounded-xl bg-paper p-4 text-sm"><summary className="cursor-pointer font-medium">What stages 1 to 3 found (data health, restatements, KPIs)</summary><pre className="mt-3 whitespace-pre-wrap break-words font-sans text-[13px] leading-relaxed text-ink">{plan.context}</pre></details>
      {plan.engine==="agent" && plan.state==="TRIAGE_REVIEW" && <div className={`mt-4 rounded-xl p-4 text-sm ${plan.flagged?"bg-amberbg text-amber":"bg-agentbg text-agentdeep"}`}>
        <p className="font-medium">{plan.flagged ? "The manager's plan is flagged for your review" : "The manager kept code's plan"}<span className="font-normal"> · agent ({plan.model})</span></p>
        {plan.flags?.map((f,i)=><p key={i} className="mt-1">{f}</p>)}
        {plan.corrections?.map((f,i)=><p key={`c${i}`} className="mt-1 text-ink"><span className="font-medium">Rule applied by code:</span> {f}</p>)}
        {plan.manager_note && <p className="mt-1 text-ink">Manager's note: {plan.manager_note}</p>}
      </div>}
    </div>
    {plan.state==="OUT_OF_SCOPE" ? <div className="rounded-xl bg-amberbg px-6 py-5 text-sm text-amber ring-1 ring-amberline"><p className="font-medium">The data cannot answer this question as asked.</p><p className="mt-1">{plan.scope}</p><p className="mt-2 text-ink">The brief will state this and give the scripted brief for the week. No investigation runs.</p></div> :
    plan.state!=="TRIAGE_REVIEW" ? <div className="rounded-xl bg-sheet px-6 py-5 text-sm border border-rule">{plan.state==="CALENDAR" ? "Calendar week: lower volume is expected, so code opens no story." : "Routine week: code found no material change, so there is no story to triage."}</div> :
    <ol className="space-y-3">{order.map((id, i)=>{ const c=byId.get(id)!; const on=kept.has(id); return <li key={id} className={`rounded-xl bg-sheet p-5 ring-1 transition ${on?"ring-rule":"opacity-60 ring-rule"}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0"><div className="text-[11px] uppercase tracking-widest text-muted">{on ? `Story ${decision.stories.indexOf(id)+1}` : "Left out"} · code rank {c.rank}</div><h3 className="mt-1 text-base font-semibold">{c.title}</h3></div>
        <div className="flex shrink-0 items-center gap-1">
          <button aria-label={`Move ${c.title} up`} disabled={i===0} onClick={()=>move(id,-1)} className="rounded-lg px-2 py-1 text-sm border border-rule disabled:opacity-30">↑</button>
          <button aria-label={`Move ${c.title} down`} disabled={i===order.length-1} onClick={()=>move(id,1)} className="rounded-lg px-2 py-1 text-sm border border-rule disabled:opacity-30">↓</button>
          <label className="ml-2 flex items-center gap-2 text-sm"><input type="checkbox" checked={on} onChange={()=>toggle(id)}/>Investigate</label>
        </div>
      </div>
      <p className="mt-3 text-sm leading-relaxed">{c.what_moved}</p>
      {c.manager && <p className="mt-2 rounded-lg bg-agentbg px-3 py-2 text-[13px] text-agentdeep"><span className="font-medium">Manager (agent):</span> {c.manager.keep ? `keeps it as story ${c.manager.position}` : `drops it${c.manager.why ? `: ${c.manager.why}` : ""}`}{c.manager.hypotheses.length ? ` · tests in this order: ${c.manager.hypotheses.join(", ")}` : ""}</p>}
      <dl className="mt-3 grid gap-x-4 gap-y-2 text-[13px] sm:grid-cols-[110px_1fr]">{QUESTIONS.map(([k,label])=><div key={k} className="contents"><dt className="font-medium text-muted">{label}</dt><dd className="leading-relaxed">{c[k]}</dd></div>)}</dl>
    </li>})}</ol>}
    {(over.length>0 || plan.dropped.length>0) && <div className="rounded-xl bg-sheet/70 px-6 py-5 text-sm border border-rule">
      <h3 className="font-semibold">Dropped by code</h3><p className="mt-1 text-xs text-muted">These follow the rules; they cannot be added back to this brief.</p>
      <ul className="mt-3 space-y-1.5">{over.map(c=><li key={c.id}><span className="font-medium">{c.title}</span> <span className="text-muted">· over the story cap of this brief</span></li>)}{plan.dropped.map(d=><li key={d.territory}><span className="font-medium">{d.territory}</span> <span className="text-muted">· {d.reason}</span></li>)}</ul>
    </div>}
    <div className="flex flex-wrap items-center gap-3">
      <button disabled={busy} onClick={()=>onApprove(decision)} className={BTN}>{plan.state!=="TRIAGE_REVIEW" ? "Write the brief" : changed ? "Approve my changes and investigate" : "Approve plan and investigate"}</button>
      {changed && <span className="text-xs text-muted">Your changes are recorded as your calls in the brief's triage record.</span>}
    </div>
  </div>
}

// brief-002 US7: who did each of the seven stages (Briefing Architecture §6 states, §9 modes).
const ACTOR = {code:["Code","bg-paper text-ink border border-rule"], agent:["Agent","bg-agentbg text-agentdeep"], llm:["LLM step","bg-amberbg text-amber"], human:["Person","bg-humanbg text-human"]} as const

function FlowPanel({flow, triage}: {flow: Stage[], triage?: TriageRecord | null}) {
  return <details className="rounded-xl bg-sheet px-6 py-5 border border-rule">
    <summary className="cursor-pointer text-sm font-semibold">How this brief was made</summary>
    <ol className="mt-4 space-y-3">{flow.map(s=><li key={s.stage} className="grid gap-1 sm:grid-cols-[28px_1fr]">
      <span className="font-mono text-xs text-muted">{s.stage}</span>
      <div><div className="flex flex-wrap items-center gap-2"><span className="text-sm font-medium">{s.name}</span>{s.states.map(st=><span key={st} className="rounded bg-paper px-1.5 py-0.5 font-mono text-[10px] text-muted border border-rule">{st}</span>)}</div>
        <div className="mt-1 flex flex-wrap gap-1.5">{s.actors.length ? s.actors.map((a,i)=><span key={i} className={`${chip} ${ACTOR[a.kind][1]}`}>{ACTOR[a.kind][0]}: {a.name}</span>) : <span className="text-xs text-muted">Skipped</span>}</div>
        <p className="mt-1 text-xs text-muted">{s.note}</p></div>
    </li>)}</ol>
    {triage && <div className="mt-5 border-t border-rule pt-4"><h4 className="text-xs font-semibold uppercase tracking-wider text-muted">Triage record</h4>
      <ul className="mt-2 space-y-1 text-xs">{triage.calls.map((c,i)=><li key={i} className="flex flex-wrap items-center gap-2"><span className={`${chip} ${ACTOR[c.layer][1]}`}>{({human:"You",agent:"Manager",code:"Code"} as const)[c.layer]}</span><span className="font-medium">{c.title}</span><span className="text-muted">{({investigated:"investigated as proposed",moved:c.layer==="agent"?"moved by the manager":"moved by you",dropped:c.layer==="agent"?`left out by the manager${c.why?`: ${c.why}`:""}`:"left out by you",restored:"put back by you after the manager dropped it",over_cap:"over the story cap",quiet:"within its normal range",withheld:"withheld at the feed gate"} as Record<string,string>)[c.outcome] ?? c.outcome}{c.position?` · story ${c.position}`:""}</span></li>)}</ul></div>}
  </details>
}

// Inline citations: every number in the brief is a claim; the server says where each one sits.
function CitedText({result, onOpen}: {result: BriefingResult, onOpen: (evidenceId: string) => void}) {
  const spans = [...(result.citations ?? [])].sort((a,b)=>a.start-b.start)
  if (!spans.length) return <>{result.answer}</>
  const parts: ReactNode[] = []
  let pos = 0
  spans.forEach((sp, i) => {
    const claim: Claim | undefined = result.claims[sp.claim]
    if (!claim || sp.start < pos || result.answer.slice(sp.start, sp.end) !== claim.value) return
    parts.push(result.answer.slice(pos, sp.start))
    parts.push(<button key={i} type="button" onClick={()=>onOpen(claim.evidence_id)} title={`Source ${claim.evidence_id}: open the query behind ${claim.value}`}
      className="rounded-sm font-medium underline decoration-agent/40 decoration-dotted underline-offset-4 hover:bg-agentbg focus:bg-agentbg focus:outline-none">{claim.value}<sup className="ml-px font-mono text-[9px] font-normal text-agentdeep">{claim.evidence_id.replace(/^e/, "")}</sup></button>)
    pos = sp.end
  })
  parts.push(result.answer.slice(pos))
  return <>{parts}</>
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
  return <>
    <div className="flex justify-end"><ViewToggle value={mode} onChange={v=>{ if (v==="analyst") setMode("analyst"); else void showPreview() }}/></div>
    {mode==="leadership" ? (previewError ? <div role="alert" className="rounded-xl bg-amberbg px-5 py-4 text-sm text-amber">{previewError}</div> : preview ? <SummaryCard brief={preview} preview/> : <p className="text-sm text-muted">Loading the leadership view…</p>) :
    <article className={`${PANEL} overflow-hidden`}>
      <div className="border-b border-rule px-6 py-5">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 text-xs text-muted"><span>{result.engine==="agent" ? "Agent team · experimental" : "Scripted"}</span><ClassLabel tab="briefing.view.analyst"/></div>
        <h2 className="mt-2 text-2xl">{labelTerritory(result.territory_id)}, week of {labelWeek(result.week_start)}</h2>
        <p className="mt-1.5 text-sm text-muted">{result.brand_id}</p>
        <div className="mt-3 flex flex-wrap items-center gap-2"><span key={result.review_status} className={`${REVIEW_CHIP[result.review_status][0]} inline-flex items-center gap-1 pa-fade`}>{result.review_status==="approved" && <svg viewBox="0 0 24 24" className="pa-draw h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>}{REVIEW_CHIP[result.review_status][1]}</span>{result.abstained && <span className={`${chip} bg-amberbg text-amber`}>Unresolved findings</span>}</div>
      </div>
      <div className="px-6 py-6"><div className="max-w-[68ch] whitespace-pre-wrap break-words font-serif text-[16px] leading-[1.7] text-ink"><CitedText result={result} onOpen={setEvidenceId}/></div>
        <p className="mt-4 text-[11px] text-muted">Each underlined number is a claim: click it, or its source number, to open the query and record behind it.</p></div>
      <section className="flex flex-wrap items-center justify-between gap-2 border-t border-rule bg-paper/60 px-6 py-3">
        {result.evidence.length>0 ? <button className="flex items-center gap-2 text-xs font-medium text-agentdeep underline-offset-4 hover:underline" onClick={()=>setEvidenceId(result.evidence[0].id)}><Icon name="evidence"/>All {result.evidence.length} sources ({result.claims.length} numbers)</button> : <span className="text-xs text-muted">No numeric claims in this brief.</span>}
        <span className="rounded bg-sheet px-2 py-1 font-mono text-[11px] text-muted border border-rule" title="Pinned data version">{result.data_version??"Version unavailable"}</span>
      </section>
      <ReviewPanel result={result} onChange={onChange}/>
    </article>}
    {mode==="analyst" && <AnswerFeedback lane="briefing" refId={result.brief_id} view="analyst"/>}
    {mode==="analyst" && result.flow && <FlowPanel flow={result.flow} triage={result.triage}/>}
    <InsightButton briefId={result.brief_id} view={mode}/>
    {evidenceId && <EvidenceDrawer result={result} selectedId={evidenceId} onClose={()=>setEvidenceId(null)}/>}
  </>
}

function AnalystApp({me}: {me: Me}) {
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
  // Agent engine (core-007 FR-028/FR-031): jobs run on teammate or cloud CPU hosts; the app only queues them.
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
  // The job's real state, from the server: queued, then running, then done (shown by JobProgress).
  const [jobState,setJobState] = useState<{kind: "triage" | "brief", status: "queued" | "running"} | null>(null)
  const describeJob = (job: AgentJob) => {
    if (job.status === "queued" || job.status === "running") {
      setJobState({kind: job.kind === "triage" ? "triage" : "brief", status: job.status})
      setJobNote(job.status === "queued" && !agent?.online && !(agent?.cloud?.enabled && agent.cloud.seconds_left > 0)
        ? "Waiting for the agent team to become available…"
        : job.status === "running" && job.host_kind === "cloud_cpu" ? `On the cloud CPU host: allow about ${agent?.cloud?.eta_minutes ?? 15} minutes.` : null)
      return
    }
    setJobState(null)
    setJobNote(null)
  }

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
    finally {setPending(false);setJobNote(null);setJobState(null)}
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
    finally {setPending(false);setJobNote(null);setJobState(null)}
  }
  const openApproved = async (id: string) => {
    setRunError(null);setResult(null);setRequestScope(null);setView("result");setPending(true)
    try { setResult(await openBrief(id, "analyst")) } catch(e) { setRunError(message(e)) } finally { setPending(false) }
  }
  const selectable = !!context && !loadingContext && !pending
  return <Shell me={me} onBriefingHome={()=>setView("home")}>
    <div className="workspace-content pt-8 sm:pt-10">{(view==="home" || view==="approved") && <Greeting detail={context ? `Data through ${labelWeek(context.latest_week)}, across ${context.territory_ids.length} territories.` : undefined}/>}<SubTabs label="Weekly briefing" value={view==="approved" ? "approved" : "new"} onChange={t=>setView(t==="approved" ? "approved" : "home")} options={[["new","New briefing","briefing.new"],["approved","Approved briefings","briefing.approved"]] as const}/></div>
    {view==="home" ? <div key="home" className="workspace-content pa-stagger space-y-5 py-8">
      <p className="text-sm text-muted">Generate the week's brand-performance briefing, check its evidence, and approve it for the Brand Director.</p>
      {contextError && <div role="alert" className="rounded-xl bg-amberbg p-4 text-sm text-amber"><strong>Backend unavailable.</strong> {contextError}<button className="mt-2 block underline" onClick={()=>void refresh()}>Retry connection</button></div>}
      <form onSubmit={submit} className={`${PANEL} space-y-6 p-6`} aria-busy={loadingContext}>
        <div className="grid gap-4 sm:grid-cols-3">
          <label className={LABEL}>Brand
            <select className={FIELD} value={brand} onChange={e=>setBrand(e.target.value)} disabled={!selectable}>{context?.product_ids.map(id=><option key={id} value={id}>{id}</option>)}</select>
          </label>
          <label className={LABEL}>Territory
            <select className={FIELD} value={territory} onChange={e=>setTerritory(e.target.value)} disabled={!selectable}>{context?.territory_ids.map(id=><option key={id} value={id}>{labelTerritory(id)}</option>)}</select>
          </label>
          <label className={LABEL}>Reporting week
            <select className={FIELD} value={week} onChange={e=>setWeek(e.target.value)} disabled={!selectable}>{[...(context?.available_weeks??[])].reverse().map(w=><option key={w} value={w}>{labelWeek(w)}</option>)}</select>
          </label>
        </div>
        <fieldset><legend className="mb-1.5 text-xs font-medium text-muted">Engine</legend>
          <div className="divide-y divide-rule rounded-lg border border-rule">
            <label className="flex cursor-pointer items-start gap-3 px-4 py-3 transition-colors hover:bg-paper/50"><input type="radio" name="engine" checked={engine==="scripted"} onChange={()=>setEngine("scripted")} className="mt-1"/><span><span className={`block text-sm ${engine==="scripted" ? "text-ink" : "text-muted"}`}>Scripted</span><span className="block text-xs text-muted">Instant. Runs the standard checks in a fixed order.</span></span></label>
            <label className={`flex items-start gap-3 px-4 py-3 transition-colors ${agent?.configured===false ? "cursor-not-allowed opacity-50" : "cursor-pointer hover:bg-paper/50"}`}><input type="radio" name="engine" checked={engine==="agent"} disabled={agent?.configured===false} onChange={()=>setEngine("agent")} className="mt-1"/><span title={agent?.model ? `Model: ${agent.model}` : undefined}><span className={`block text-sm ${engine==="agent" ? "text-ink" : "text-muted"}`}>Agent team <span className="text-xs text-muted">· experimental</span></span><span className="block text-xs text-muted">A manager and two specialist agents investigate the week. {agent?.builtin ? "Usually a minute or two." : agent?.online ? "A few minutes per step." : agent?.cloud?.enabled && agent.cloud.seconds_left>0 ? `About ${agent.cloud.eta_minutes ?? 15} minutes for a brief.` : "Waits until an agent host is available."}</span></span></label>
          </div>
        </fieldset>
        {engine==="agent" && <label className={LABEL}>Your question (optional)
          <textarea value={ask} onChange={e=>setAsk(e.target.value)} maxLength={300} rows={2} placeholder="For example: why did Pacific drop, and is anything else going on?" className={FIELD}/>
        </label>}
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-rule pt-4">
          <span className="text-xs text-muted">{loadingContext ? "Loading the data release…" : engine==="agent" ? "You review the agents' plan before they investigate." : "You review the plan before the checks run."}</span>
          <button type="submit" disabled={!selectable} className={BTN}>Generate briefing</button>
        </div>
      </form>
    </div> : view==="approved" ? <div key="approved" className="workspace-content pa-fade space-y-4 py-8"><p className="text-sm text-muted">What the Brand Director can open, on the current data release.</p><PublishedList onOpen={id=>void openApproved(id)}/></div>
    : <div className="workspace-content space-y-6 py-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <button className="flex items-center gap-1.5 text-sm text-agentdeep hover:underline" onClick={()=>setView("home")}><Icon name="back"/>Change scope</button>
        {requestScope && <span className="text-xs text-muted">{requestScope.brand} · {labelTerritory(requestScope.territory)} · week of {labelWeek(requestScope.week)}</span>}
      </div>
      {pending && (jobState
        ? <JobProgress kind={jobState.kind} status={jobState.status} note={jobNote}/>
        : <div role="status" className="space-y-3"><span className="sr-only">{view === "triage" ? "Preparing the triage plan…" : "Preparing the briefing…"}</span>
            <div className="pa-skeleton h-5 w-2/5"/><div className={`${PANEL} space-y-3 p-6`}><div className="pa-skeleton h-6 w-3/5"/><div className="pa-skeleton h-3 w-full"/><div className="pa-skeleton h-3 w-11/12"/><div className="pa-skeleton h-3 w-4/5"/></div></div>)}
      {runError && <div role="alert" className="rounded-xl bg-amberbg px-5 py-4 text-sm text-amber"><strong>{view==="triage" ? "The triage plan could not be built." : "Briefing could not be generated."}</strong><p className="mt-2">{runError}</p><p className="mt-2">No mock result was substituted.</p>{view==="result" && plan && <button className="mt-2 underline" onClick={()=>{setRunError(null);setView("triage")}}>Back to the triage plan</button>}</div>}
      {view==="triage" && plan && !pending && <TriageReview plan={plan} busy={pending} onApprove={d=>void approvePlan(d)}/>}
      {view==="result" && result && <AnalystBrief result={result} onChange={setResult}/>}
    </div>}
  </Shell>
}

function LeaderApp({me}: {me: Me}) {
  const [brief,setBrief] = useState<LeadershipBrief | null>(null)
  const [error,setError] = useState<string | null>(null)
  const [loading,setLoading] = useState(false)
  const open = async (id: string) => {
    setLoading(true); setError(null)
    try { setBrief(await openBrief(id, "leadership")) } catch(e) { setError(message(e)) } finally { setLoading(false) }
  }
  return <Shell me={me} onBriefingHome={()=>{setBrief(null);setError(null)}}>
    <div className="workspace-content space-y-6 py-8 sm:py-10">
      {brief || loading || error ? <>
        <button className="flex items-center gap-2 text-sm text-agentdeep hover:underline" onClick={()=>{setBrief(null);setError(null)}}><Icon name="back"/>All approved briefings</button>
        {loading && <p role="status" className="text-sm text-muted">Opening the briefing…</p>}
        {error && <div role="alert" className="rounded-xl bg-amberbg px-5 py-4 text-sm text-amber">{error}</div>}
        {brief && <><SummaryCard brief={brief}/><InsightButton briefId={brief.brief_id} view="leadership"/></>}
      </> : <><Greeting detail="Executive summaries the Commercial Analyst has reviewed and approved."/><div className="flex flex-wrap items-baseline justify-between gap-3 border-b border-rule pb-3"><h2 className="text-xl">Approved briefings</h2><ClassLabel tab="briefing.approved"/></div><PublishedList onOpen={id=>void open(id)}/></>}
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
    if (me.lanes.forecast?.available) return <Shell me={me} startInForecast>{null}</Shell>
    return <Centered>
      <h1 className="mt-5 text-lg font-semibold">No access</h1>
      <p className="mt-2 text-sm text-muted">Your account has no PharmAgentics role. Ask the project owner to assign one.</p>
      <a className="mt-5 inline-block text-sm font-medium text-agentdeep hover:underline" href="/auth/logout">Sign out</a>
    </Centered>
  }
  return briefing.actions.includes("run") ? <AnalystApp me={me}/> : <LeaderApp me={me}/>
}
