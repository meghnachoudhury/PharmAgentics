import { useEffect, useMemo, useRef, useState, type ReactNode } from "react"
import { getOverview, type Evidence, type Overview as O, type Stat, type TerritoryRow, type WeekPoint } from "./agent/overviewApi"
import { Icon } from "./agent/primitives"

const PANEL = "rounded-xl border border-rule bg-sheet"
const BTN = "inline-flex items-center justify-center gap-2 rounded-lg bg-navy px-4 py-2 text-sm font-medium text-onaccent transition-[background-color,transform] duration-150 hover:bg-navyhover active:scale-[0.98]"
const int = (v: number | null | undefined) => (v == null ? "–" : Math.round(v).toLocaleString())
const pct = (v: number | null | undefined, signed = true) =>
  v == null ? "–" : `${signed && v > 0 ? "+" : ""}${(v * 100).toFixed(1)}%`
const day = (iso: string) => new Date(`${iso}T00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })
const STATUS = { material: "Material change", normal: "Within normal range", held_back: "Held back" } as const

function Drawer({ title, kicker, onClose, children }: { title: string, kicker: string, onClose: () => void, children: ReactNode }) {
  const close = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null
    close.current?.focus()
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose() }
    document.addEventListener("keydown", esc)
    return () => { document.removeEventListener("keydown", esc); opener?.focus() }
  }, [onClose])
  return <div className="fixed inset-0 z-40 flex justify-end">
    <button className="absolute inset-0 bg-black/60" aria-label="Close panel" tabIndex={-1} onClick={onClose}/>
    <aside role="dialog" aria-modal="true" aria-labelledby="overview-drawer-title" className="pa-slide relative z-10 flex h-full w-full max-w-lg flex-col border-l border-rule bg-sheet">
      <div className="flex items-start justify-between gap-3 border-b border-rule p-5">
        <div><div className="text-[11px] uppercase tracking-[0.06em] text-muted">{kicker}</div><h2 id="overview-drawer-title" className="mt-1 font-serif text-xl">{title}</h2></div>
        <button ref={close} onClick={onClose} aria-label="Close panel" className="rounded-lg p-2 hover:bg-paper"><Icon name="close" className="h-4 w-4"/></button>
      </div>
      <div className="min-h-0 flex-1 space-y-6 overflow-y-auto p-5">{children}</div>
    </aside>
  </div>
}

function Query({ ev }: { ev: Evidence }) {
  const scope = typeof ev.params.scope === "string" ? ev.params.scope : ev.tool
  return <li className="py-3">
    <div className="flex items-baseline justify-between gap-3 text-sm"><span>{scope}</span><span className="tabular-nums text-muted">{String(ev.result)}</span></div>
    <pre className="mt-2 overflow-x-auto whitespace-pre-wrap break-words rounded-lg bg-paper p-3 font-mono text-[11px] leading-relaxed text-muted">{ev.query}</pre>
  </li>
}

function Sparkline({ points, label }: { points: number[], label: string }) {
  if (points.length < 2) return <span className="text-xs text-muted">–</span>
  const lo = Math.min(...points), hi = Math.max(...points), w = 96, h = 28, pad = 3
  const x = (i: number) => pad + (i * (w - 2 * pad)) / (points.length - 1)
  const y = (v: number) => (hi === lo ? h / 2 : h - pad - ((v - lo) * (h - 2 * pad)) / (hi - lo))
  return <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} role="img" aria-label={label} className="shrink-0 text-muted">
    <polyline points={points.map((v, i) => `${x(i)},${y(v)}`).join(" ")} fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round"/>
    <circle cx={x(points.length - 1)} cy={y(points[points.length - 1])} r="2.5" className="fill-ink"/>
  </svg>
}

function WeekChart({ series, field, label, baseline }: { series: WeekPoint[], field: "trx" | "nrx" | "nbrx", label: string, baseline: string[] }) {
  const [hover, setHover] = useState<number | null>(null)
  const vals = series.map(p => p[field])
  if (vals.length < 2) return null
  const w = 440, h = 96, padX = 4, padY = 8
  const lo = Math.min(...vals), hi = Math.max(...vals)
  const x = (i: number) => padX + (i * (w - 2 * padX)) / (vals.length - 1)
  const y = (v: number) => (hi === lo ? h / 2 : h - padY - ((v - lo) * (h - 2 * padY)) / (hi - lo))
  const base = series.map((p, i) => (baseline.includes(p.week) ? i : -1)).filter(i => i >= 0)
  const shown = hover ?? vals.length - 1
  const pick = (clientX: number, el: SVGSVGElement) => {
    const r = el.getBoundingClientRect()
    setHover(Math.max(0, Math.min(vals.length - 1, Math.round(((clientX - r.left) / r.width) * (vals.length - 1)))))
  }
  return <figure>
    <figcaption className="flex items-baseline justify-between gap-3 text-sm">
      <span>{label}</span><span className="tabular-nums text-muted">{day(series[shown].week)}: <span className="text-ink">{int(vals[shown])}</span></span>
    </figcaption>
    <svg viewBox={`0 0 ${w} ${h}`} className="mt-2 h-24 w-full touch-none" preserveAspectRatio="none" role="img"
      aria-label={`${label}, ${series.length} weeks, from ${int(vals[0])} to ${int(vals[vals.length - 1])}`}
      onPointerMove={e => pick(e.clientX, e.currentTarget)} onPointerLeave={() => setHover(null)}>
      {base.length > 0 && <rect x={x(base[0])} width={x(base[base.length - 1]) - x(base[0])} y={0} height={h} className="fill-rule/50"/>}
      <polyline points={vals.map((v, i) => `${x(i)},${y(v)}`).join(" ")} fill="none" className="stroke-agent" strokeWidth="2" vectorEffect="non-scaling-stroke" strokeLinejoin="round"/>
      <line x1={x(shown)} x2={x(shown)} y1={0} y2={h} className="stroke-muted/40" strokeWidth="1" vectorEffect="non-scaling-stroke"/>
    </svg>
    <div className="mt-1 flex justify-between text-[11px] text-muted"><span>{day(series[0].week)}</span><span>Shaded: the 4 comparison weeks</span><span>{day(series[series.length - 1].week)}</span></div>
  </figure>
}

function TerritoryPanel({ t, o, onClose, onGenerate }: { t: TerritoryRow, o: O, onClose: () => void, onGenerate: () => void }) {
  const sentence = t.status === "held_back"
    ? "Not judged this week: a feed-health flag in this week or the 4 comparison weeks keeps it out of like-for-like comparison, as in the brief."
    : `${t.change != null && t.change < 0 ? "Down" : "Up"} ${pct(Math.abs(t.change ?? 0), false)} on the 4 weeks before; its normal range is ±${pct(t.threshold, false)}. `
      + `Against the other territories: ${t.gap != null && t.gap > 0 ? "+" : ""}${((t.gap ?? 0) * 100).toFixed(1)} points.${t.status === "material" ? " Both are past the triage rule, so the brief will open a story on it." : ""}`
  const evidence = o.evidence.filter(e => t.evidence_ids.includes(e.id))
  return <Drawer kicker={`${STATUS[t.status]} · week of ${day(o.week)}`} title={t.label} onClose={onClose}>
    <p className="text-sm leading-relaxed">{sentence}</p>
    <button className={BTN} onClick={onGenerate}>Generate brief for {t.label}</button>
    <section className="space-y-5">
      <WeekChart series={t.series} field="trx" label="TRx" baseline={o.baseline}/>
      <WeekChart series={t.series} field="nrx" label="NRx" baseline={o.baseline}/>
      <WeekChart series={t.series} field="nbrx" label="New patients (NBRx)" baseline={o.baseline}/>
    </section>
    <section><h3 className="text-sm font-semibold">Product mix this week</h3><p className="mt-0.5 text-xs text-muted">Competitive intelligence: TRx by product in {t.label}.</p>
      <table className="mt-2 w-full text-sm"><thead className="text-left text-xs text-muted"><tr><th className="py-1 font-medium">Product</th><th className="py-1 text-right font-medium">TRx</th><th className="py-1 text-right font-medium">Share</th></tr></thead>
        <tbody>{t.mix.map(m => <tr key={m.product} className="border-t border-rule"><td className="py-1.5">{m.name}{m.product === o.product ? " (our brand)" : ""}</td><td className="py-1.5 text-right tabular-nums">{int(m.trx)}</td><td className="py-1.5 text-right tabular-nums">{pct(m.share, false)}</td></tr>)}</tbody></table>
    </section>
    <section><h3 className="text-sm font-semibold">Data health this week</h3>
      {t.health ? <dl className="mt-2 grid grid-cols-2 gap-y-1 text-sm">
        <dt className="text-muted">Status</dt><dd className="text-right">{t.health.status === "PASS" ? "Pass" : "Flagged"}</dd>
        <dt className="text-muted">Missing keys</dt><dd className="text-right tabular-nums">{int(t.health.missing_keys)}</dd>
        <dt className="text-muted">Duplicate keys</dt><dd className="text-right tabular-nums">{int(t.health.duplicate_keys)}</dd>
        {!!t.health.reasons.length && <><dt className="text-muted">Reasons</dt><dd className="text-right">{t.health.reasons.join(", ")}</dd></>}
      </dl> : <p className="mt-2 text-sm text-muted">No feed record for this week.</p>}
    </section>
    <section><h3 className="text-sm font-semibold">Queries behind this panel</h3><p className="mt-0.5 text-xs text-muted">Pinned data version {o.data_version}</p><ul className="divide-y divide-rule">{evidence.map(e => <Query key={e.id} ev={e}/>)}</ul></section>
  </Drawer>
}

function StatBar({ stats, onOpen }: { stats: Stat[], onOpen: (s: Stat) => void }) {
  return <section aria-label="This week" className={`${PANEL} grid grid-cols-2 lg:grid-cols-4`}>
    {stats.map((s, i) => <button key={s.key} onClick={() => onOpen(s)}
      className={`group p-5 text-left transition-colors hover:bg-paper/60 ${i % 2 ? "border-l border-rule" : ""} ${i > 1 ? "border-t border-rule lg:border-t-0" : ""} ${i === 2 ? "lg:border-l" : ""}`}>
      <div className="text-xs text-muted">{s.label}</div>
      <div className="mt-2 font-serif text-3xl tabular-nums">{s.value}</div>
      <div className={`mt-1.5 text-xs tabular-nums ${s.adverse ? "text-amber" : "text-muted"}`}>
        {s.key === "material" ? `of ${s.change?.value ?? "–"} like-for-like territories`
          : s.key === "health" ? (s.raw ? "flagged feeds this week" : "every feed passed")
          : s.change ? `${s.adverse ? "Down " : s.change.raw && s.change.raw >= 0.05 ? "Up " : ""}${s.change.value.replace("-", "")} on the prior week` : "no prior week"}
      </div>
      <div className="mt-2 text-[11px] text-muted opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100">Show the query</div>
    </button>)}
  </section>
}

function Strip({ t, domain, onOpen }: { t: TerritoryRow, domain: number, onOpen: () => void }) {
  const pos = (v: number) => `${50 + (v / domain) * 50}%`
  if (t.status === "held_back" || t.change == null || t.threshold == null)
    return <div className="relative h-7"><div className="absolute inset-y-1 left-1/2 w-px bg-rule"/><span className="absolute inset-y-0 left-2 flex items-center text-xs text-muted">not judged</span></div>
  const size = 10 + Math.min(8, Math.sqrt(Math.max(t.trx ?? 0, 0)) / 4)
  return <div className="relative h-7">
    <div className="absolute inset-y-1.5 rounded bg-rule/70" style={{ left: pos(-t.threshold), right: `calc(100% - ${pos(t.threshold)})` }}/>
    <div className="absolute inset-y-0 left-1/2 w-px bg-muted/40"/>
    <button onClick={onOpen} aria-label={`${t.label}: ${pct(t.change)} against a normal range of ±${pct(t.threshold, false)}; ${STATUS[t.status]}`}
      title={`${t.label}: ${pct(t.change)} (normal range ±${pct(t.threshold, false)}), ${int(t.trx)} TRx`}
      className={`absolute top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-agent outline-offset-2 ${t.status === "material" ? "bg-agent" : "bg-sheet"}`}
      style={{ left: pos(Math.max(-domain, Math.min(domain, t.change))), width: size, height: size }}/>
  </div>
}

function Territories({ o, onOpen }: { o: O, onOpen: (t: TerritoryRow) => void }) {
  const domain = useMemo(() => {
    const m = Math.max(0.15, ...o.territories.flatMap(t => [Math.abs(t.change ?? 0), t.threshold ?? 0]))
    return Math.ceil(m * 1.1 * 10) / 10
  }, [o])
  const ticks = [-domain, -domain / 2, 0, domain / 2, domain]
  const cols = "grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 md:grid-cols-[11rem_96px_minmax(0,1fr)_4.5rem_4.5rem]"
  return <section className={PANEL} aria-labelledby="territories-title">
    <div className="flex flex-wrap items-baseline justify-between gap-2 px-5 pt-5">
      <h3 id="territories-title" className="text-sm font-semibold">Territories to look at</h3>
      <p className="text-xs text-muted"><span aria-hidden className="mr-1 inline-block h-2.5 w-2.5 rounded-full bg-agent align-middle"/>material change
        <span aria-hidden className="ml-3 mr-1 inline-block h-2.5 w-2.5 rounded-full border-2 border-agent align-middle"/>within normal range
        <span aria-hidden className="ml-3 mr-1 inline-block h-2.5 w-5 rounded bg-rule align-middle"/>the territory's normal range</p>
    </div>
    <p className="px-5 pt-1 text-xs leading-relaxed text-muted">Week of {day(o.week)} against the 4 weeks before. A change is material when it is past the territory's own normal range (at least {pct(o.rule.material_change, false)}, wider where weekly volume is noisy) and at least {(o.rule.material_gap * 100).toFixed(0)} points apart from the other territories: the rule the brief's triage uses.</p>
    <div className={`${cols} mt-4 border-b border-rule px-5 pb-2 text-[11px] text-muted`}>
      <span>Territory</span><span className="hidden md:block">13 weeks of TRx</span>
      <span className="relative hidden h-4 md:block">{ticks.map((v, i) => <span key={v} style={{ left: `${50 + (v / domain) * 50}%` }}
        className={`absolute tabular-nums ${i === 0 ? "" : i === ticks.length - 1 ? "-translate-x-full" : "-translate-x-1/2"}`}>{v > 0 ? "+" : ""}{Math.round(v * 100)}%</span>)}</span>
      <span className="hidden text-right md:block">TRx</span><span className="text-right">Change</span>
    </div>
    <ul className="divide-y divide-rule">
      {o.territories.map(t => <li key={t.id} className={`${cols} px-5 py-3`}>
        <button onClick={() => onOpen(t)} className="min-w-0 text-left">
          <span className="block truncate text-sm hover:underline">{t.label}</span>
          <span className={`block text-xs ${t.status === "material" ? "text-ink" : "text-muted"}`}>{STATUS[t.status]}</span>
        </button>
        <span className="hidden md:block"><Sparkline points={t.series.map(p => p.trx)} label={`${t.label} TRx over ${t.series.length} weeks`}/></span>
        <span className="col-span-2 row-start-2 mt-2 md:col-span-1 md:row-start-auto md:mt-0"><Strip t={t} domain={domain} onOpen={() => onOpen(t)}/></span>
        <span className="hidden text-right text-sm tabular-nums md:block">{int(t.trx)}</span>
        <span className="col-start-2 row-start-1 text-right text-sm tabular-nums md:col-start-auto md:row-start-auto">{pct(t.change)}</span>
      </li>)}
    </ul>
  </section>
}

export function Overview({ weeks, onGenerate }: { weeks: string[], onGenerate: (territory: string, week: string) => void }) {
  const [week, setWeek] = useState<string | undefined>(undefined)
  const [o, setO] = useState<O | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState<{ kind: "territory", t: TerritoryRow } | { kind: "stat", s: Stat } | null>(null)
  useEffect(() => {
    let live = true
    setError(null)
    getOverview(week).then(v => { if (live) setO(v) }, e => { if (live) setError(e instanceof Error ? e.message : String(e)) })
    return () => { live = false }
  }, [week])
  const stat = open?.kind === "stat" ? open.s : null
  const statEvidence = stat && o ? o.evidence.filter(e => e.id === stat.evidence_id || e.id === stat.change?.evidence_id) : []
  return <><div className="workspace-wide pa-stagger space-y-6 py-8">
    <div className="flex flex-wrap items-end justify-between gap-4">
      <p className="text-sm text-muted">{o ? `${o.product_name} (${o.product}), week of ${day(o.week)}. Every figure is computed from the governed data; select one to see its query.` : "Loading the week…"}</p>
      <label className="flex items-center gap-2 text-xs text-muted">Week
        <select value={week ?? o?.week ?? ""} onChange={e => setWeek(e.target.value)} className="rounded-lg border border-rule bg-paper px-2.5 py-1.5 text-sm text-ink">
          {[...weeks].reverse().map(w => <option key={w} value={w}>{day(w)}</option>)}
        </select>
      </label>
    </div>
    {error && <div role="alert" className="rounded-xl bg-amberbg p-4 text-sm text-amber">{error}</div>}
    {o?.note && <p className="text-sm text-amber">{o.note}</p>}
    {!o && !error && <div className="pa-skeleton h-32 rounded-xl"/>}
    {o && <StatBar stats={o.stats} onOpen={s => setOpen({ kind: "stat", s })}/>}
    {o && <Territories o={o} onOpen={t => setOpen({ kind: "territory", t })}/>}
  </div>
    {o && open?.kind === "territory" && <TerritoryPanel t={open.t} o={o} onClose={() => setOpen(null)} onGenerate={() => onGenerate(open.t.id, o.week)}/>}
    {o && stat && <Drawer kicker={`Week of ${day(o.week)}`} title={`${stat.label}: ${stat.value}`} onClose={() => setOpen(null)}>
      <p className="text-sm text-muted">Pinned data version {o.data_version}</p>
      <ul className="divide-y divide-rule">{statEvidence.map(e => <Query key={e.id} ev={e}/>)}</ul>
    </Drawer>}
  </>
}
