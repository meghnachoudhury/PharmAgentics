// Forecast driver recovery on the Evaluation page (fcst-002): does each system accept the drivers that act in a
// window, and no others? Rules against the model investigator (the comparison arm). Exported by `eval drivers`.
// Shown only to Forecast roles: anyone else gets 403 from the route and this renders nothing.
import { useEffect, useState } from "react"
import { forecastDrivers, type DriverBoard } from "./agent/forecastApi"

const PANEL = "rounded-xl border border-rule bg-sheet"
const CHIP = "rounded-full px-2 py-0.5 text-[11px] font-medium"
const SYSTEM: Record<string, string> = { forecast_rules: "Rules investigate (the default)", forecast_investigator: "Model investigates (comparison arm)" }

export function ForecastDriverRecovery() {
  const [board, setBoard] = useState<DriverBoard | null>(null)
  useEffect(() => { forecastDrivers().then(setBoard, () => setBoard(null)) }, [])
  const systems = Object.entries(board?.systems ?? {}).sort(([a], [b]) => (a === "forecast_rules" ? -1 : b === "forecast_rules" ? 1 : 0))
  if (!systems.length) return null
  return <div className="space-y-4">
    <div className="pt-2"><h3 className="text-xs uppercase tracking-[0.06em] text-muted">Forecast driver recovery</h3>
      <p className="mt-1 text-sm text-muted">Each probe asks for the drivers of the miss in a window where the user stories say which drivers act, or that none does. A hit accepts exactly those. This compares the rules with a model as investigator; the product uses the rules. Labels are a {board?.labels} until the Forecast team confirms them.</p></div>
    {systems.map(([key, sys]) => <section key={key} className={`${PANEL} p-6`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2"><h4 className="text-sm font-semibold">{SYSTEM[key] ?? key}{sys.model ? ` · ${sys.model}` : ""}</h4><span className="text-xs text-muted">run {sys.run_id} · {sys.exported.replace("T", " ")}</span></div>
      <dl className="mt-4 grid grid-cols-3 divide-x divide-rule border-y border-rule">{[["Drivers recovered", `${Math.round(sys.metrics.driver_recall * 100)}%`], ["False drivers", String(sys.metrics.false_drivers)], ["Exact answers", `${Math.round(sys.metrics.exact_set_share * sys.metrics.probes)} of ${sys.metrics.probes}`]].map(([k, v]) => <div key={k} className="px-4 py-3 first:pl-0"><dt className="text-xs text-muted">{k}</dt><dd className="mt-0.5 text-lg font-medium tabular-nums">{v}</dd></div>)}</dl>
      <div className="mt-4 overflow-x-auto"><table className="text-xs tabular-nums"><thead><tr><th className="pr-4 text-left font-medium text-muted">true \ accepted</th>{sys.drivers.map(d => <th key={d} className="px-3 text-right font-medium text-muted">{d}</th>)}</tr></thead>
        <tbody>{sys.drivers.map(t => <tr key={t}><td className="py-1 pr-4 text-muted">{t}</td>{sys.drivers.map(d => { const n = sys.confusion[t]?.[d] ?? 0; return <td key={d} className={`px-3 py-1 text-right ${n ? (t === d ? "font-medium text-ink" : "font-medium text-amber") : "text-muted"}`}>{n}</td> })}</tr>)}</tbody></table></div>
      <details className="mt-4"><summary className="cursor-pointer text-sm">Every probe</summary>
        <ul className="mt-2 divide-y divide-rule text-sm">{sys.probes.map(p => { const ok = [...p.expect].sort().join() === [...p.got].sort().join(); return <li key={p.id} className="flex flex-wrap items-baseline justify-between gap-2 py-2"><span className="min-w-0"><span className={`${CHIP} mr-2 ${ok ? "bg-paper text-muted" : "bg-amberbg text-amber"}`}>{ok ? "hit" : "miss"}</span>{p.question}</span><span className="text-xs text-muted">expected {p.expect.join(", ") || "none"} · accepted {p.got.join(", ") || "none"}</span></li> })}</ul></details>
    </section>)}
  </div>
}
