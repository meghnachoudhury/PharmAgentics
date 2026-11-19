// Evaluation telemetry: how each system scored on the golden set, from the snapshot exported out of MLflow.
import { useEffect, useState } from "react"
import { getTelemetry, type Telemetry as T, type TelemetryRun } from "./agent/briefingApi"

const NAMES: Record<string, string> = { briefing_agent: "Briefing agent", briefing_scripted: "Briefing, scripted baseline",
  briefing_lowcode: "Briefing, low-code agent", forecast_scripted: "Forecast, scripted baseline",
  reference: "Reference answers (control)", naive_llm: "Model without data (control)" }
const label = (k: string) => k.replace(/_/g, " ").replace(/^./, c => c.toUpperCase())
const pct = (v: number) => (v <= 1 && v >= 0 ? `${Math.round(v * 100)}%` : v.toFixed(2))
const when = (iso: string) => new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })
const name = (r: TelemetryRun) => NAMES[r.system] ?? r.system

function Card({ r }: { r: TelemetryRun }) {
  const rows = Object.entries(r.metrics)
  return <section className="rounded-xl border border-rule bg-sheet p-6">
    <div className="flex flex-wrap items-baseline justify-between gap-2">
      <h3 className="text-sm font-semibold">{name(r)}{r.model ? ` · ${r.model}` : ""}</h3>
      <span className="text-xs text-muted">{when(r.started)} · {r.cases} questions · {r.reruns} rerun{r.reruns > 1 ? "s" : ""}{r.minutes != null ? ` · ${r.minutes} min` : ""}</span>
    </div>
    <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-1.5 sm:grid-cols-2">
      {rows.map(([k, v]) => <div key={k} className="flex items-baseline justify-between gap-3 border-b border-rule py-1 text-sm">
        <dt className="text-muted">{label(k)}</dt><dd className="tabular-nums">{pct(v)}</dd></div>)}
    </dl>
    {!!Object.keys(r.judge_metrics).length && <p className="mt-3 text-xs text-muted">Judge scores (report only): {Object.entries(r.judge_metrics).map(([k, v]) => `${label(k)} ${pct(v)}`).join(" · ")}</p>}
    <p className="mt-3 font-mono text-[11px] text-muted">run {r.run_id} · code {r.code_version || "n/a"} · data {r.data_version || "n/a"}</p>
  </section>
}

export function TelemetryWorkspace() {
  const [t, setT] = useState<T | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => { getTelemetry().then(setT, e => setErr(e instanceof Error ? e.message : String(e))) }, [])
  const systems = t?.latest.filter(r => !r.control) ?? []
  const controls = t?.latest.filter(r => r.control) ?? []
  const cell = (v: number | undefined) => (v != null ? pct(v) : "–")
  return <div className="workspace-content space-y-6 pb-12 pt-8 sm:pt-10">
    <header><h2 className="font-serif text-2xl font-medium">Evaluation</h2>
      <p className="mt-1.5 text-sm text-muted">How each version scored on the golden questions{t?.exported ? `, exported ${when(t.exported)}` : ""}. {t?.note}</p></header>
    {err && <div role="alert" className="rounded-xl bg-amberbg p-4 text-sm text-amber">{err}</div>}
    {!t && !err && <p className="text-sm text-muted">Loading…</p>}
    {t && !t.latest.length && <p className="text-sm text-muted">No evaluation runs have been exported yet.</p>}
    {systems.map(r => <Card key={r.run_id} r={r}/>)}
    {!!controls.length && <><h3 className="pt-2 text-xs uppercase tracking-widest text-muted">Controls</h3>{controls.map(r => <Card key={r.run_id} r={r}/>)}</>}
    {!!t?.runs.length && <details className="rounded-xl border border-rule bg-sheet p-6"><summary className="cursor-pointer text-sm font-semibold">All runs ({t.runs.length})</summary>
      <div className="mt-3 overflow-x-auto"><table className="w-full text-left text-sm">
        <thead className="text-xs text-muted"><tr><th className="py-1 pr-4 font-medium">Date</th><th className="pr-4 font-medium">System</th><th className="pr-4 font-medium">Lane</th><th className="pr-4 font-medium">Number recall</th><th className="font-medium">Claims reconcile</th></tr></thead>
        <tbody>{t.runs.map(r => <tr key={r.run_id} className="border-t border-rule"><td className="py-1 pr-4 tabular-nums">{when(r.started)}</td><td className="pr-4">{name(r)}</td><td className="pr-4">{r.lane}</td>
          <td className="pr-4 tabular-nums">{cell(r.metrics.golden_number_recall)}</td><td className="tabular-nums">{cell(r.metrics.claims_reconcile)}</td></tr>)}</tbody>
      </table></div></details>}
  </div>
}
