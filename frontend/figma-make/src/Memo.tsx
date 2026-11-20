// brief-003: the weekly brief as a memo. Sections, charts and the data behind them come from the server;
// nothing here computes a number. Charts are plain SVG drawn from the points the server returns.
import { useState, type ReactNode } from "react"
import type { ChartPoint, ChartSpec, Claim, DataTable, Evidence, MemoSection, Span } from "./agent/briefingApi"

const COLORS = ["var(--color-agent)", "var(--color-human)"]
const PANEL_COLOR = "var(--color-amber)"

function Cited({text, spans, claims, onOpen}: {text: string, spans?: Span[], claims?: Claim[], onOpen?: (evidenceId: string) => void}) {
  const sorted = [...(spans ?? [])].sort((a, b) => a.start - b.start)
  if (!sorted.length || !claims || !onOpen) return <>{text}</>
  const parts: ReactNode[] = []
  let pos = 0
  sorted.forEach((sp, i) => {
    const claim = claims[sp.claim]
    if (!claim || sp.start < pos || text.slice(sp.start, sp.end) !== claim.value) return
    parts.push(text.slice(pos, sp.start))
    parts.push(<button key={i} type="button" onClick={() => onOpen(claim.evidence_id)} title={`Source ${claim.evidence_id}: open the query behind ${claim.value}`}
      className="rounded-sm font-medium underline decoration-agent/40 decoration-dotted underline-offset-4 hover:bg-agentbg focus:bg-agentbg focus:outline-none">{claim.value}<sup className="ml-px font-mono text-[9px] font-normal text-agentdeep">{claim.evidence_id.replace(/^e/, "")}</sup></button>)
    pos = sp.end
  })
  parts.push(text.slice(pos))
  return <>{parts}</>
}

function shortWeek(iso: string): string {
  const d = new Date(`${iso}T00:00:00`)
  return d.toLocaleDateString(undefined, {month: "short", day: "numeric"})
}

function fmt(v: number, unit = "count"): string {
  if (unit === "rate") return v.toFixed(2)
  if (unit === "percent") return `${v.toFixed(1)}%`
  return Math.round(v).toLocaleString()
}

const W = 640, H = 200, PAD = {l: 48, r: 12, t: 12, b: 26}

function scale(values: number[], lo?: number, hi?: number) {
  const vs = values.concat(lo ?? [], hi ?? [])
  let min = Math.min(...vs), max = Math.max(...vs)
  if (min === max) { min -= 1; max += 1 }
  const pad = (max - min) * 0.08
  return {min: min - pad, max: max + pad, y: (v: number) => PAD.t + (H - PAD.t - PAD.b) * (1 - (v - (min - pad)) / ((max + pad) - (min - pad)))}
}

function LineChart({weeks, series, band, unit = "count", label}: {weeks: string[], series: {name: string, points: ChartPoint[], color: string}[], band?: ChartSpec["band"], unit?: string, label: string}) {
  const values = series.flatMap(s => s.points.map(p => p.value).filter((v): v is number => v !== null))
  if (!values.length) return null
  const sc = scale(values, band?.low, band?.high)
  const x = (w: string) => PAD.l + (W - PAD.l - PAD.r) * (weeks.length < 2 ? 0.5 : weeks.indexOf(w) / (weeks.length - 1))
  const ticks = [weeks[0], weeks[Math.floor((weeks.length - 1) / 2)], weeks[weeks.length - 1]]
  return <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label={label}>
    {band && <g><rect x={PAD.l} width={W - PAD.l - PAD.r} y={sc.y(band.high)} height={Math.max(1, sc.y(band.low) - sc.y(band.high))} fill="var(--color-agent)" opacity={0.1}/>
      <text x={W - PAD.r} y={sc.y(band.high) - 3} textAnchor="end" className="fill-muted text-[10px]">baseline band</text></g>}
    {[sc.min, (sc.min + sc.max) / 2, sc.max].map((v, i) => <g key={i}>
      <line x1={PAD.l} x2={W - PAD.r} y1={sc.y(v)} y2={sc.y(v)} stroke="var(--color-rule)"/>
      <text x={PAD.l - 6} y={sc.y(v) + 3} textAnchor="end" className="fill-muted text-[10px]">{fmt(v, unit)}</text></g>)}
    {ticks.map((w, i) => <text key={i} x={x(w)} y={H - 8} textAnchor="middle" className="fill-muted text-[10px]">{shortWeek(w)}</text>)}
    {series.map((s, si) => {
      const pts = s.points.filter(p => p.value !== null)
      return <g key={si}>
        <polyline fill="none" stroke={s.color} strokeWidth={2} points={pts.map(p => `${x(p.week)},${sc.y(p.value as number)}`).join(" ")}/>
        {pts.map((p, i) => {
          const assumed = p.basis && p.basis !== "observed"
          return <circle key={i} cx={x(p.week)} cy={sc.y(p.value as number)} r={assumed || p.restated ? 4.5 : 3}
            fill={assumed ? "var(--color-sheet)" : s.color} stroke={s.color} strokeWidth={1.5} strokeDasharray={p.restated ? "2 2" : undefined}>
            <title>{`${s.name}, week of ${p.week}: ${fmt(p.value as number, unit)}${assumed ? ` (${p.basis}, an assumption)` : ""}${p.restated ? " (restated)" : ""}`}</title>
          </circle>
        })}
      </g>
    })}
  </svg>
}

function Legend({items}: {items: {label: string, color: string, hollow?: boolean}[]}) {
  return <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted">
    {items.map((it, i) => <span key={i} className="inline-flex items-center gap-1.5">
      <svg viewBox="0 0 10 10" className="h-2.5 w-2.5" aria-hidden="true"><circle cx="5" cy="5" r="4" fill={it.hollow ? "none" : it.color} stroke={it.color} strokeWidth="1.5"/></svg>{it.label}</span>)}
  </div>
}

function CoverageStrip({chart}: {chart: ChartSpec}) {
  const rows = chart.rows ?? []
  const cell = 14, left = 108, top = 4
  const width = left + chart.weeks.length * cell + 4, height = top + rows.length * cell + 18
  return <svg viewBox={`0 0 ${width} ${height}`} className="h-auto w-full max-w-[520px]" role="img" aria-label="Feed coverage by territory and week">
    {rows.map((r, ri) => <g key={r.territory}>
      <text x={left - 6} y={top + ri * cell + 10} textAnchor="end" className="fill-muted text-[9px]">{r.territory}</text>
      {r.cells.map(c => {
        const cx = left + chart.weeks.indexOf(c.week) * cell, cy = top + ri * cell
        return <g key={c.week}>
          <rect x={cx + 1} y={cy + 1} width={cell - 2} height={cell - 2} rx={2}
            fill={c.basis === "observed" ? "var(--color-agent)" : "var(--color-sheet)"} opacity={c.basis === "observed" ? 0.35 : 1}
            stroke={c.basis === "observed" ? "none" : "var(--color-amber)"} strokeWidth={1.2}/>
          {c.basis === "estimated" && <path d={`M${cx + 3} ${cy + 3}L${cx + cell - 3} ${cy + cell - 3}M${cx + cell - 3} ${cy + 3}L${cx + 3} ${cy + cell - 3}`} stroke="var(--color-amber)" strokeWidth={1.2}/>}
          {c.restated && <circle cx={cx + cell / 2} cy={cy + cell / 2} r={cell / 2 - 0.5} fill="none" stroke="var(--color-human)" strokeWidth={1.2}/>}
          <title>{`${r.territory}, week of ${c.week}: ${c.basis}${c.basis !== "observed" ? ", an assumption" : ""}${c.restated ? ", restated" : ""}`}</title>
        </g>
      })}
    </g>)}
    {[chart.weeks[0], chart.weeks[chart.weeks.length - 1]].map((w, i) => <text key={i} x={left + (i ? chart.weeks.length - 1 : 0) * cell + cell / 2} y={height - 4} textAnchor="middle" className="fill-muted text-[9px]">{shortWeek(w)}</text>)}
  </svg>
}

function ChartBlock({chart, onOpen, claims, explanationSpans}: {chart: ChartSpec, onOpen?: (id: string) => void, claims?: Claim[], explanationSpans?: Span[]}) {
  const series = (chart.series ?? []).map((s, i) => ({...s, color: COLORS[i % COLORS.length]}))
  return <figure className="my-4 rounded-xl border border-rule bg-paper/40 p-4">
    {chart.kind === "coverage" ? <CoverageStrip chart={chart}/> : <>
      <LineChart weeks={chart.weeks} series={series} band={chart.band} unit={chart.kind === "share" ? "percent" : "count"} label={chart.caption}/>
      <Legend items={series.map((s): {label: string, color: string, hollow?: boolean} => ({label: s.name, color: s.color})).concat(series.some(s => s.points.some(p => p.basis && p.basis !== "observed")) ? [{label: "projected or estimated (an assumption)", color: "var(--color-muted)", hollow: true}] : [])}/>
      {chart.panel && chart.panel.points.length > 0 && <div className="mt-3 border-t border-rule pt-3">
        <p className="mb-1 text-[11px] uppercase tracking-wider text-muted">{chart.panel.name}</p>
        <LineChart weeks={chart.weeks} series={[{name: chart.panel.name, points: chart.panel.points, color: PANEL_COLOR}]} unit={chart.panel.unit} label={chart.panel.name}/>
      </div>}
    </>}
    <figcaption className="mt-3 text-[13px] leading-relaxed text-muted">{chart.caption}</figcaption>
    <p className="mt-1 text-[14px] leading-relaxed text-ink"><Cited text={chart.explanation} spans={explanationSpans} claims={claims} onOpen={onOpen}/></p>
  </figure>
}

function csv(table: DataTable): string {
  const cell = (v: unknown) => { const s = v === null || v === undefined ? "" : String(v); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s }
  return [table.columns.map(cell).join(","), ...table.rows.map(r => r.map(cell).join(","))].join("\n")
}

function download(name: string, table: DataTable) {
  const url = URL.createObjectURL(new Blob([csv(table)], {type: "text/csv"}))
  const a = document.createElement("a")
  a.href = url; a.download = name; a.click()
  URL.revokeObjectURL(url)
}

function TableView({table, name}: {table: DataTable, name: string}) {
  const [sql, setSql] = useState(false)
  // A table whose rows each carry their own query (the claims) shows that column only on "Show query"; the CSV keeps it.
  const perRow = table.columns.includes("query")
  const shown = table.columns.map((_, j) => j).filter(j => sql || table.columns[j] !== "query")
  return <div className="rounded-lg border border-rule">
    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-rule px-3 py-2 text-xs">
      <span className="font-mono text-agentdeep">{table.evidence_id}</span>
      <span className="flex gap-3">
        <button type="button" className="text-agentdeep hover:underline" onClick={() => setSql(!sql)} aria-expanded={sql}>{sql ? "Hide query" : "Show query"}</button>
        <button type="button" className="text-agentdeep hover:underline" onClick={() => download(name, table)}>Download CSV</button>
      </span>
    </div>
    {sql && !perRow && <pre className="overflow-x-auto whitespace-pre-wrap break-all border-b border-rule bg-paper p-3 font-mono text-[11px] leading-relaxed">{table.query}</pre>}
    <div className="max-h-64 overflow-auto">
      <table className="w-full text-left font-mono text-[11px]">
        <thead className="sticky top-0 bg-sheet text-muted"><tr>{shown.map(j => <th key={j} className="px-3 py-1.5 font-normal">{table.columns[j]}</th>)}</tr></thead>
        <tbody>{table.rows.map((r, i) => <tr key={i} className="border-t border-rule/60 align-top">{shown.map(j => <td key={j} className={`px-3 py-1 ${table.columns[j] === "query" ? "whitespace-pre-wrap break-all text-muted" : ""}`}>{r[j] === null ? "" : String(r[j])}</td>)}</tr>)}</tbody>
      </table>
    </div>
  </div>
}

function DataBehind({section, claims, evidence, briefId}: {section: MemoSection, claims: Claim[], evidence: Evidence[], briefId: string}) {
  const tables = [section.chart?.table, section.chart?.panel?.table].filter((t): t is DataTable => !!t)
  const used = (section.claims ?? []).map(i => claims[i]).filter((c): c is Claim => !!c)
  if (!tables.length && !used.length) return null
  const byId = new Map(evidence.map(e => [e.id, e]))
  const claimTable: DataTable | null = used.length ? {
    evidence_id: "Numbers in this section", query: "",
    columns: ["value", "evidence_id", "tool", "query"],
    rows: used.map(c => [c.value, c.evidence_id, byId.get(c.evidence_id)?.tool ?? "", byId.get(c.evidence_id)?.query ?? ""]),
  } : null
  return <details className="mt-3 rounded-xl bg-paper/60 px-4 py-3 text-sm">
    <summary className="cursor-pointer text-xs font-medium text-agentdeep">Data behind this section ({used.length} number{used.length === 1 ? "" : "s"}{tables.length ? `, ${tables.length} chart table${tables.length > 1 ? "s" : ""}` : ""})</summary>
    <div className="mt-3 space-y-3">
      {claimTable && <TableView table={claimTable} name={`brief-${briefId}-section-${section.number}-claims.csv`}/>}
      {tables.map(t => <TableView key={t.evidence_id} table={t} name={`brief-${briefId}-section-${section.number}-${t.evidence_id}.csv`}/>)}
    </div>
  </details>
}

// The memo: numbered sections in order. Analysts get inline citations and the data behind each section;
// leaders get the server's cut (no claims, tables or queries) through the same component.
export function Memo({sections, briefId, claims, evidence, onOpen, onAsk}: {sections: MemoSection[], briefId: string, claims?: Claim[], evidence?: Evidence[], onOpen?: (evidenceId: string) => void, onAsk?: (chip: {number: string, title: string}) => void}) {
  // A section with subsections (§3 and its stories) shows its own lines (left out, considered and dropped) after
  // them, in the order the memo's text gives them.
  const body = (s: MemoSection) => <>
    {s.text && <div className="mt-2 max-w-[68ch] whitespace-pre-wrap break-words font-serif text-[16px] leading-[1.7] text-ink"><Cited text={s.text} spans={s.text_citations} claims={claims} onOpen={onOpen}/></div>}
    {s.prose && <p className="mt-2 max-w-[68ch] font-serif text-[16px] italic leading-[1.7] text-ink"><Cited text={s.prose} spans={s.prose_citations} claims={claims} onOpen={onOpen}/></p>}
    {s.chart && <ChartBlock chart={s.chart} claims={claims} onOpen={onOpen} explanationSpans={s.chart.explanation_citations}/>}
    {claims && evidence && <DataBehind section={s} claims={claims} evidence={evidence} briefId={briefId}/>}
  </>
  const heading = (s: MemoSection, sub: boolean) => <div className="flex items-baseline justify-between gap-3">
    <h3 id={`memo-${briefId}-${s.number}`} className={`scroll-mt-24 ${sub ? "text-base font-semibold" : "text-lg font-semibold"}`}>
      <span className="mr-2 font-mono text-sm text-muted">§{s.number}</span>{s.title}</h3>
    {onAsk && <button type="button" onClick={() => onAsk({number: s.number, title: s.title})} className="shrink-0 text-xs text-agentdeep hover:underline">Ask about this</button>}
  </div>
  return <div className="space-y-7">
    {sections.filter(s => !s.number.includes(".")).map(s => {
      const children = sections.filter(c => c.number.startsWith(`${s.number}.`))
      return <section key={s.number} aria-labelledby={`memo-${briefId}-${s.number}`}>
        {heading(s, false)}
        {children.length > 0 && <div className="mt-4 space-y-6">{children.map(c =>
          <section key={c.number} aria-labelledby={`memo-${briefId}-${c.number}`} className="border-l-2 border-rule pl-4">{heading(c, true)}{body(c)}</section>)}</div>}
        <div className={children.length ? "mt-4" : ""}>{body(s)}</div>
      </section>
    })}
  </div>
}
