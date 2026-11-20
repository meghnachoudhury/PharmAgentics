import { useEffect, useState, type ReactNode } from "react"
import { getTelemetry, getUsage, type LaneUsage, type Spread, type Telemetry as T, type TelemetryRun, type Usage } from "./agent/telemetryApi"

const PANEL = "rounded-xl border border-rule bg-sheet"
const NAMES: Record<string, string> = {
  briefing_agent: "Briefing agent", briefing_scripted: "Briefing, scripted baseline", briefing_lowcode: "Briefing, low-code agent",
  forecast_scripted: "Forecast, scripted baseline", reference: "Reference answers (control)", naive_llm: "Model without data (control)",
}
const label = (k: string) => k.replace(/[_.]/g, " ").replace(/^./, c => c.toUpperCase())
const pct = (v: number) => (v <= 1 && v >= 0 ? `${Math.round(v * 100)}%` : v.toFixed(2))
const when = (iso: string) => new Date(/^\d{4}-\d{2}-\d{2}$/.test(iso) ? `${iso}T00:00` : iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })
const name = (r: TelemetryRun) => NAMES[r.system] ?? r.system
const list = (o: Record<string, number> | undefined) => Object.entries(o ?? {}).map(([k, v]) => `${v} ${k}`).join(", ") || "none"
const spread = (s: Spread | undefined, unit: string, scale = 1) =>
  s ? `${((s.p50 ?? 0) / scale).toFixed(1)} ${unit} · p95 ${((s.p95 ?? 0) / scale).toFixed(1)} ${unit}` : "no data yet"

function Heading({ title, note }: { title: string, note?: ReactNode }) {
  return <div className="pt-2"><h3 className="text-xs uppercase tracking-[0.06em] text-muted">{title}</h3>{note && <p className="mt-1 text-sm text-muted">{note}</p>}</div>
}

function Figures({ items }: { items: [string, string, string][] }) {
  return <section aria-label="Headline figures" className={`${PANEL} grid grid-cols-2 lg:grid-cols-4`}>
    {items.map(([k, v, sub], i) => <div key={k} className={`p-5 ${i % 2 ? "border-l border-rule" : ""} ${i > 1 ? "border-t border-rule lg:border-t-0" : ""} ${i === 2 ? "lg:border-l" : ""}`}>
      <div className="text-xs text-muted">{k}</div><div className="mt-2 font-serif text-3xl tabular-nums">{v}</div><div className="mt-1.5 text-xs text-muted">{sub}</div>
    </div>)}
  </section>
}

function Rows({ rows }: { rows: [string, ReactNode][] }) {
  return <dl className="grid grid-cols-1 gap-x-8 sm:grid-cols-2">
    {rows.map(([k, v]) => <div key={k} className="flex items-baseline justify-between gap-3 border-b border-rule py-1.5 text-sm"><dt className="text-muted">{k}</dt><dd className="text-right tabular-nums">{v}</dd></div>)}
  </dl>
}

function laneRows(lane: "briefing" | "forecast", u: LaneUsage): [string, ReactNode][] {
  const rows: [string, ReactNode][] = [
    [lane === "briefing" ? "Briefs requested" : "Forecast explanations run", u.requests],
    ["Opened", u.opens], ["Review decisions", list(u.decisions)], ["Answer votes", `${u.votes.up} up, ${u.votes.down} down`],
  ]
  if (lane === "briefing") rows.push(["Engines", list(u.engines)], ["Scripted response time", spread(u.scripted_ms, "s", 1000)],
    ["Agent jobs", list(u.agent_jobs)], ["Agent brief, queue to result", spread(u.agent_seconds, "s")])
  return rows
}

function InUse({ u }: { u: Usage }) {
  const lanes = (["briefing", "forecast"] as const).filter(l => u.lanes[l])
  return <>
    <Heading title="In use" note={`${u.since ? `Since ${when(u.since)}.` : "No use recorded yet."} Test-login activity is left out (${u.excluded_test_records} record${u.excluded_test_records === 1 ? "" : "s"}). Updated every 5 minutes.`}/>
    <section className={`${PANEL} divide-y divide-rule`}>
      {lanes.map(l => {
        const weeks = Object.entries(u.lanes[l]!.weekly)
        return <div key={l} className="p-5"><h4 className="text-sm font-semibold">{l === "briefing" ? "Weekly briefing" : "Forecast explanation"}</h4>
          <div className="mt-2"><Rows rows={laneRows(l, u.lanes[l]!)}/></div>
          {!!weeks.length && <p className="mt-3 text-xs text-muted">Requests by week: {weeks.map(([w, n]) => `week of ${when(w)}: ${n}`).join(" · ")}</p>}
        </div>
      })}
      <div className="p-5"><h4 className="text-sm font-semibold">Ratings</h4><div className="mt-2"><Rows rows={[
        ["Sessions rated", list(u.sessions)],
        ["System Usability Scale", u.sus ? `${u.sus.mean} of 100 (${u.sus.n} responses)` : "no responses yet"],
        ...(u.cloud_seconds ? [["Cloud agent time this month", `${u.cloud_seconds.used.toLocaleString()} of ${u.cloud_seconds.limit.toLocaleString()} s`] as [string, ReactNode]] : []),
      ]}/></div></div>
    </section>
  </>
}

function Scores({ runs }: { runs: TelemetryRun[] }) {
  const cell = (v: number | undefined) => (v != null ? pct(v) : "–")
  return <section className={PANEL}>
    <div className="hidden grid-cols-[minmax(0,1fr)_7rem_6rem_6rem] gap-4 border-b border-rule px-5 py-2 text-[11px] text-muted sm:grid">
      <span>System</span><span>Run</span><span className="text-right">Claims reconcile</span><span className="text-right">Number recall</span>
    </div>
    <ul className="divide-y divide-rule">{runs.map(r => <li key={r.run_id}>
      <details>
        <summary className="grid cursor-pointer list-none grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-1 px-5 py-3 hover:bg-paper/60 sm:grid-cols-[minmax(0,1fr)_7rem_6rem_6rem]">
          <span className="min-w-0"><span className="block truncate text-sm">{name(r)}</span>{r.model && <span className="block truncate text-xs text-muted">{r.model}</span>}</span>
          <span className="text-xs text-muted sm:text-sm">{when(r.started)}</span>
          <span className="text-sm tabular-nums sm:text-right"><span className="text-xs text-muted sm:hidden">Claims </span>{cell(r.metrics.claims_reconcile)}</span>
          <span className="text-right text-sm tabular-nums"><span className="text-xs text-muted sm:hidden">Recall </span>{cell(r.metrics.golden_number_recall)}</span>
        </summary>
        <div className="px-5 pb-4">
          <p className="mb-2 text-xs text-muted">{r.cases} questions · {r.reruns} rerun{r.reruns > 1 ? "s" : ""}{r.minutes != null ? ` · ${r.minutes} min` : ""} · run {r.run_id} · code {r.code_version || "n/a"} · data {r.data_version || "n/a"}</p>
          <Rows rows={Object.entries(r.metrics).map(([k, v]) => [label(k), pct(v)])}/>
          {!!Object.keys(r.judge_metrics).length && <p className="mt-3 text-xs text-muted">Judge scores (report only): {Object.entries(r.judge_metrics).map(([k, v]) => `${label(k)} ${pct(v)}`).join(" · ")}</p>}
        </div>
      </details>
    </li>)}</ul>
  </section>
}

export function TelemetryWorkspace() {
  const [t, setT] = useState<T | null>(null)
  const [u, setU] = useState<Usage | null>(null)
  const [err, setErr] = useState<string[]>([])
  useEffect(() => {
    const fail = (e: unknown) => setErr(x => [...x, e instanceof Error ? e.message : String(e)])
    getTelemetry().then(setT, fail)
    getUsage().then(setU, fail)
  }, [])
  const b = u?.lanes.briefing ?? u?.lanes.forecast
  const reviewed = b ? Object.values(b.decisions).reduce((x, y) => x + y, 0) : 0
  const approved = b ? (b.decisions.approved ?? b.decisions.approve ?? 0) : 0
  const lead = t?.latest.find(r => !r.control)
  return <div className="workspace-wide pa-stagger space-y-6 pb-12 pt-8 sm:pt-10">
    <header><h2 className="font-serif text-2xl font-medium">Evaluation</h2>
      <p className="mt-1.5 text-sm text-muted">How PharmAgentics is used, and how each version scored on the golden questions.</p></header>
    {err.map(e => <div key={e} role="alert" className="rounded-xl bg-amberbg p-4 text-sm text-amber">{e}</div>)}
    {!t && !u && !err.length && <div className="pa-skeleton h-32 rounded-xl"/>}
    {u && b && <Figures items={[
      [u.lanes.briefing ? "Briefs requested" : "Explanations run", String(b.requests), u.since ? `since ${when(u.since)}` : "none yet"],
      ["Approved", reviewed ? `${Math.round((approved / reviewed) * 100)}%` : "–", reviewed ? `${approved} of ${reviewed} reviewed` : "nothing reviewed yet"],
      ["Typical response", b.scripted_ms ? `${((b.scripted_ms.p50 ?? 0) / 1000).toFixed(1)} s` : "–", b.scripted_ms ? "scripted engine, median" : "no timed requests"],
      ["Usability (SUS)", u.sus ? String(u.sus.mean) : "–", u.sus ? `of 100, ${u.sus.n} responses` : "no responses yet"],
    ]}/>}
    {u && <InUse u={u}/>}
    {t && <>
      <Heading title="Golden-set scores" note={<>{t.exported ? `Exported ${when(t.exported)}. ` : ""}{t.note}{lead ? ` Latest: ${name(lead)}, ${when(lead.started)}.` : ""} Select a row for every score.</>}/>
      <Scores runs={t.latest.filter(r => !r.control)}/>
      {t.latest.some(r => r.control) && <><Heading title="Controls"/><Scores runs={t.latest.filter(r => r.control)}/></>}
      {!!t.runs.length && <details className={`${PANEL} p-5`}><summary className="cursor-pointer text-sm font-semibold">All runs ({t.runs.length})</summary>
        <div className="mt-3 overflow-x-auto"><table className="w-full text-left text-sm">
          <thead className="text-xs text-muted"><tr><th className="py-1 pr-4 font-medium">Date</th><th className="pr-4 font-medium">System</th><th className="pr-4 font-medium">Lane</th><th className="pr-4 font-medium">Number recall</th><th className="font-medium">Claims reconcile</th></tr></thead>
          <tbody>{t.runs.map(r => <tr key={r.run_id} className="border-t border-rule"><td className="py-1 pr-4 tabular-nums">{when(r.started)}</td><td className="pr-4">{name(r)}</td><td className="pr-4">{r.lane}</td>
            <td className="pr-4 tabular-nums">{r.metrics.golden_number_recall != null ? pct(r.metrics.golden_number_recall) : "–"}</td><td className="tabular-nums">{r.metrics.claims_reconcile != null ? pct(r.metrics.claims_reconcile) : "–"}</td></tr>)}</tbody>
        </table></div></details>}
    </>}
  </div>
}
