import { useEffect, useState, type ReactNode } from "react"
import { getTelemetry, getUsage, type LaneUsage, type Spread, type Telemetry as T, type TelemetryRun, type Usage } from "./agent/telemetryApi"

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

function Card({ title, aside, children }: { title: string, aside?: string, children: ReactNode }) {
  return <section className="rounded-xl border border-rule bg-sheet p-6">
    <div className="flex flex-wrap items-baseline justify-between gap-2"><h3 className="text-sm font-semibold">{title}</h3>{aside && <span className="text-xs text-muted">{aside}</span>}</div>
    {children}
  </section>
}

function Rows({ rows }: { rows: [string, ReactNode][] }) {
  return <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-1.5 sm:grid-cols-2">
    {rows.map(([k, v]) => <div key={k} className="flex items-baseline justify-between gap-3 border-b border-rule py-1 text-sm"><dt className="text-muted">{k}</dt><dd className="text-right tabular-nums">{v}</dd></div>)}
  </dl>
}

function LaneCard({ lane, u }: { lane: "briefing" | "forecast", u: LaneUsage }) {
  const rows: [string, ReactNode][] = [
    [lane === "briefing" ? "Briefs requested" : "Forecast explanations run", u.requests],
    ["Opened", u.opens],
    ["Review decisions", list(u.decisions)],
    ["Answer votes", `${u.votes.up} up, ${u.votes.down} down`],
  ]
  if (lane === "briefing") rows.push(
    ["Engines", list(u.engines)],
    ["Scripted response time", spread(u.scripted_ms, "s", 1000)],
    ["Agent jobs", list(u.agent_jobs)],
    ["Agent time to result", spread(u.agent_seconds, "s")],
  )
  const weeks = Object.entries(u.weekly)
  return <Card title={lane === "briefing" ? "Weekly briefing" : "Forecast explanation"}>
    <Rows rows={rows}/>
    {!!weeks.length && <p className="mt-3 text-xs text-muted">Requests by week: {weeks.map(([w, n]) => `week of ${when(w)}: ${n}`).join(" · ")}</p>}
  </Card>
}

function InUse({ u }: { u: Usage }) {
  const lanes = (["briefing", "forecast"] as const).filter(l => u.lanes[l])
  return <>
    <h3 className="pt-2 text-xs uppercase tracking-widest text-muted">In use</h3>
    <p className="-mt-3 text-sm text-muted">{u.since ? `Since ${when(u.since)}, ${u.participants} participant${u.participants === 1 ? "" : "s"}.` : "No use recorded yet."} Test-login activity is left out ({u.excluded_test_records} record{u.excluded_test_records === 1 ? "" : "s"}). Updated every 5 minutes.</p>
    {lanes.map(l => <LaneCard key={l} lane={l} u={u.lanes[l]!}/>)}
    <Card title="Ratings">
      <Rows rows={[
        ["Sessions rated", list(u.sessions)],
        ["System Usability Scale", u.sus ? `${u.sus.mean} of 100 (${u.sus.n} responses)` : "no responses yet"],
        ...(u.cloud_seconds ? [["Cloud agent time this month", `${u.cloud_seconds.used.toLocaleString()} of ${u.cloud_seconds.limit.toLocaleString()} s`] as [string, ReactNode]] : []),
      ]}/>
    </Card>
  </>
}

function ScoreCard({ r }: { r: TelemetryRun }) {
  return <Card title={`${name(r)}${r.model ? ` · ${r.model}` : ""}`} aside={`${when(r.started)} · ${r.cases} questions · ${r.reruns} rerun${r.reruns > 1 ? "s" : ""}${r.minutes != null ? ` · ${r.minutes} min` : ""}`}>
    <Rows rows={Object.entries(r.metrics).map(([k, v]) => [label(k), pct(v)])}/>
    {!!Object.keys(r.judge_metrics).length && <p className="mt-3 text-xs text-muted">Judge scores (report only): {Object.entries(r.judge_metrics).map(([k, v]) => `${label(k)} ${pct(v)}`).join(" · ")}</p>}
    <p className="mt-3 font-mono text-[11px] text-muted">run {r.run_id} · code {r.code_version || "n/a"} · data {r.data_version || "n/a"}</p>
  </Card>
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
  const systems = t?.latest.filter(r => !r.control) ?? []
  const controls = t?.latest.filter(r => r.control) ?? []
  const cell = (v: number | undefined) => (v != null ? pct(v) : "–")
  return <div className="workspace-content space-y-6 pb-12 pt-8 sm:pt-10">
    <header><h2 className="font-serif text-2xl font-medium">Evaluation</h2>
      <p className="mt-1.5 text-sm text-muted">How PharmAgentics is used, and how each version scored on the golden questions.</p></header>
    {err.map(e => <div key={e} role="alert" className="rounded-xl bg-amberbg p-4 text-sm text-amber">{e}</div>)}
    {!t && !u && !err.length && <p className="text-sm text-muted">Loading…</p>}
    {u && <InUse u={u}/>}
    {t && <>
      <h3 className="pt-2 text-xs uppercase tracking-widest text-muted">Golden-set scores</h3>
      <p className="-mt-3 text-sm text-muted">{t.exported ? `Exported ${when(t.exported)}. ` : ""}{t.note}</p>
      {systems.map(r => <ScoreCard key={r.run_id} r={r}/>)}
      {!!controls.length && <><h3 className="pt-2 text-xs uppercase tracking-widest text-muted">Controls</h3>{controls.map(r => <ScoreCard key={r.run_id} r={r}/>)}</>}
      {!!t.runs.length && <details className="rounded-xl border border-rule bg-sheet p-6"><summary className="cursor-pointer text-sm font-semibold">All runs ({t.runs.length})</summary>
        <div className="mt-3 overflow-x-auto"><table className="w-full text-left text-sm">
          <thead className="text-xs text-muted"><tr><th className="py-1 pr-4 font-medium">Date</th><th className="pr-4 font-medium">System</th><th className="pr-4 font-medium">Lane</th><th className="pr-4 font-medium">Number recall</th><th className="font-medium">Claims reconcile</th></tr></thead>
          <tbody>{t.runs.map(r => <tr key={r.run_id} className="border-t border-rule"><td className="py-1 pr-4 tabular-nums">{when(r.started)}</td><td className="pr-4">{name(r)}</td><td className="pr-4">{r.lane}</td>
            <td className="pr-4 tabular-nums">{cell(r.metrics.golden_number_recall)}</td><td className="tabular-nums">{cell(r.metrics.claims_reconcile)}</td></tr>)}</tbody>
        </table></div></details>}
    </>}
  </div>
}
