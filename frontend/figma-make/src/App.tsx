import { useEffect, useMemo, useState } from "react"
import { BrandMark, Icon } from "./agent/primitives"
import { getContext, getBriefing, type BriefingResult, type ReleaseContext, type Evidence, type Claim } from "./agent/briefingApi"

// The actual backend implements a scripted WEEKLY BRIEF. Do not imply that the
// frontend provides a general LLM chatbot, persistent reviews, or charts.
function labelTerritory(id: string): string {
  return id.toLowerCase().split("_").map(s => s[0].toUpperCase() + s.slice(1)).join(" ").replace("Mid Atlantic", "Mid-Atlantic")
}
function labelWeek(iso: string): string {
  const [y,m,d] = iso.split("-").map(Number)
  return new Date(Date.UTC(y,m-1,d)).toLocaleDateString("en-US", {year:"numeric",month:"short",day:"numeric",timeZone:"UTC"})
}
function dataText(input: unknown): string {
  return input === null || input === undefined ? "—" : typeof input === "string" ? input : JSON.stringify(input, null, 2)
}

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

export default function App() {
  const [context,setContext] = useState<ReleaseContext | null>(null)
  const [contextError,setContextError] = useState<string | null>(null)
  const [loadingContext,setLoadingContext] = useState(true)
  const [brand,setBrand] = useState("")
  const [territory,setTerritory] = useState("")
  const [week,setWeek] = useState("")
  const [pending,setPending] = useState(false)
  const [result,setResult] = useState<BriefingResult | null>(null)
  const [runError,setRunError] = useState<string | null>(null)
  const [evidenceId,setEvidenceId] = useState<string | null>(null)
  const [mobileNav,setMobileNav] = useState(false)
  const [view,setView] = useState<"home" | "result">("home")
  const [requestScope,setRequestScope] = useState<{brand:string,territory:string,week:string} | null>(null)

  const refresh = async () => {
    setLoadingContext(true); setContextError(null)
    try {
      const c=await getContext()
      setContext(c)
      setBrand(b=>c.product_ids.includes(b)?b:c.product_ids[0])
      setTerritory(t=>c.territory_ids.includes(t)?t:c.territory_ids[0])
      setWeek(w=>c.available_weeks.includes(w)?w:c.latest_week)
    } catch(e) {setContext(null);setContextError(e instanceof Error ? e.message : String(e))}
    finally {setLoadingContext(false)}
  }
  useEffect(()=>{void refresh()},[])

  const submit = async (event?: React.FormEvent) => {
    event?.preventDefault()
    if(pending || !context || !context.product_ids.includes(brand) || !context.territory_ids.includes(territory) || !context.available_weeks.includes(week)) return
    const selected={brand,territory,week}
    setPending(true);setRunError(null);setResult(null);setRequestScope(selected);setView("result")
    try {
      const response=await getBriefing({intent:"weekly_brief",brand_id:brand,territory_id:territory,week_start:week,question:"Generate the weekly brand-performance briefing."})
      setResult(response)
    } catch(e) {setRunError(e instanceof Error?e.message:String(e))}
    finally {setPending(false)}
  }
  const selectable = !!context && !loadingContext && !pending
  const claimRows=useMemo(()=>{
    if(!result)return [] as {claim:Claim,evidence:Evidence}[]
    const byId=new Map(result.evidence.map(e=>[e.id,e]))
    return result.claims.map(cl=>({claim:cl,evidence:byId.get(cl.evidence_id)!}))
  },[result])
  const side=<aside className="flex h-full w-full flex-col border-r border-rule bg-sheet/80">
    <div className="flex items-center gap-3 px-5 py-6"><BrandMark/><div><div className="text-[15px] font-semibold tracking-tight">PharmAgentics</div><div className="text-[11px] text-muted">Commercial Intelligence</div></div></div>
    <nav className="px-3" aria-label="Implemented features"><button className="flex w-full items-center gap-2 rounded-xl bg-paper px-3 py-3 text-left text-sm font-medium ring-1 ring-rule" onClick={()=>{setView("home");setMobileNav(false)}}><Icon name="briefings" className="text-agent"/>Weekly briefing</button></nav>
    <div className="mt-auto border-t border-rule px-5 py-5 text-xs text-muted"><p className="font-semibold text-ink">Connected data</p><p className="mt-2">{context ? `Synthetic release: ${labelWeek(context.first_week)} – ${labelWeek(context.latest_week)}` : (loadingContext?"Connecting to data release…":"API unavailable")}</p><p className="mt-2">Scripted baseline · No saved history or approval system</p></div>
  </aside>

  return <div className="flex h-dvh overflow-hidden bg-paper text-ink">
    <div className="hidden w-[260px] shrink-0 md:block">{side}</div>
    {mobileNav && <div className="fixed inset-0 z-30 flex md:hidden"><button aria-label="Close navigation" className="absolute inset-0 bg-ink/30" onClick={()=>setMobileNav(false)}/><div className="relative w-[280px] max-w-[85vw] bg-paper">{side}</div></div>}
    <main className="flex min-w-0 flex-1 flex-col">
      <header className="flex items-center justify-between border-b border-rule bg-sheet/80 px-5 py-3">
        <div className="flex items-center gap-3"><button className="rounded-lg p-1.5 md:hidden" aria-label="Open navigation" onClick={()=>setMobileNav(true)}><Icon name="menu"/></button><div><h1 className="text-sm font-semibold">Weekly Brand-Performance Briefing</h1><p className="text-[11px] text-muted">Evidence-backed synthetic commercial analytics</p></div></div>
        <span className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${context?"bg-okbg text-ok":"bg-amberbg text-amber"}`}>{context?"API connected":"API not ready"}</span>
      </header>
      {view==="home" ? <section className="min-h-0 flex-1 overflow-y-auto"><div className="mx-auto flex max-w-3xl flex-col px-5 pb-10 pt-[7vh] md:pt-[10vh]">
        <div className="pa-rise flex flex-col items-center text-center"><BrandMark size="lg"/><h2 className="mt-6 text-[clamp(1.9rem,4vw,2.6rem)] font-semibold tracking-tight">What should we investigate?</h2><p className="mt-3 max-w-xl text-[15px] leading-relaxed text-muted">Generate a weekly brand-performance briefing from the governed DuckDB release. Evidence and figures come from the backend, not sample fixtures.</p></div>
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
            <button type="submit" disabled={!selectable} className="flex w-full items-center justify-center gap-2 rounded-xl bg-navy px-4 py-3.5 text-sm font-semibold text-white transition hover:bg-agentdeep disabled:cursor-not-allowed disabled:bg-rule disabled:text-muted"><Icon name="send"/>Generate weekly briefing</button>
          </form>
        </div>
        <div className="mt-6 rounded-xl border border-rule bg-sheet/65 p-4 text-sm text-muted"><p className="font-medium text-ink">Implemented functionality</p><p className="mt-1 leading-relaxed">This is the deterministic Briefing baseline. It performs the same defined weekly workflow for each request; free-form agentic question answering, Forecast explanations, review approval, publishing, persistence and interactive charts are not implemented here.</p></div>
      </div></section> : <section className="min-h-0 flex-1 overflow-y-auto"><div className="mx-auto max-w-3xl space-y-5 px-5 py-7">
        <button className="flex items-center gap-2 text-sm text-agentdeep hover:underline" onClick={()=>setView("home")}><Icon name="back"/>Change scope</button>
        {requestScope && <div className="flex justify-end"><div className="max-w-[90%] rounded-2xl rounded-br-md bg-navy px-5 py-3 text-sm leading-relaxed text-white">Generate the weekly briefing for {requestScope.brand}, {labelTerritory(requestScope.territory)}, week of {labelWeek(requestScope.week)}.</div></div>}
        {pending && <div role="status" className="rounded-2xl bg-sheet px-5 py-4 text-sm text-muted ring-1 ring-rule">Running the scripted Briefing pipeline against DuckDB…</div>}
        {runError && <div role="alert" className="rounded-2xl bg-amberbg px-5 py-4 text-sm text-amber"><strong>Briefing could not be generated.</strong><p className="mt-2">{runError}</p><p className="mt-2">No mock result was substituted.</p></div>}
        {result && <article className="overflow-hidden rounded-2xl bg-sheet shadow-sm ring-1 ring-rule">
          <div className="border-b border-rule px-6 py-5"><div className="flex flex-wrap items-center gap-2"><span className="rounded bg-agentbg px-2.5 py-1 text-[11px] font-medium text-agentdeep">Scripted baseline · DuckDB</span><span className="rounded bg-amberbg px-2.5 py-1 text-[11px] font-medium text-amber">Draft · Requires analyst review</span>{result.abstained && <span className="rounded bg-amberbg px-2.5 py-1 text-[11px] font-medium text-amber">Unresolved findings</span>}</div><h2 className="mt-3 text-lg font-semibold">Weekly briefing · {labelTerritory(result.territory_id)}</h2><p className="mt-1 text-sm text-muted">{labelWeek(result.week_start)} · {result.brand_id}</p></div>
          <div className="px-6 py-6"><pre className="whitespace-pre-wrap break-words font-sans text-[14px] leading-[1.85] text-ink">{result.answer}</pre></div>
          <section className="border-t border-rule bg-paper/60 px-6 py-5"><div className="flex flex-wrap items-center justify-between gap-2"><div><h3 className="text-sm font-semibold">Evidence and numeric claims</h3><p className="mt-1 text-xs text-muted">Source queries and pinned data version supplied by the backend; no inferred chart data.</p></div><span className="rounded bg-sheet px-2 py-1 font-mono text-[11px] text-muted ring-1 ring-rule">{result.data_version??"Version unavailable"}</span></div>
          {claimRows.length > 0 ? <div className="mt-4 flex flex-wrap gap-2">{claimRows.map(({claim,evidence},idx)=><button className="flex items-center gap-2 rounded-lg bg-sheet px-3 py-2 text-xs ring-1 ring-rule transition hover:ring-agent/40" key={`${claim.evidence_id}-${idx}`} onClick={()=>setEvidenceId(evidence.id)}><span className="font-mono text-ink">{claim.value}</span><span className="text-agentdeep">{claim.evidence_id}</span><Icon name="chevronRight" className="h-3 w-3"/></button>)}</div> : <p className="mt-4 text-xs text-muted">The backend did not return numeric claims for this result.</p>}
          {result.evidence.length>0 && <button className="mt-4 flex items-center gap-2 text-xs font-medium text-agentdeep underline-offset-4 hover:underline" onClick={()=>setEvidenceId(result.evidence[0].id)}><Icon name="evidence"/>Browse all {result.evidence.length} evidence records</button>}
          </section>
          <div className="border-t border-rule px-6 py-4 text-xs text-muted">Not submitted, approved, published or stored by the backend. Analyst review must occur outside this interface.</div>
        </article>}
      </div></section>}
    </main>
    {result && evidenceId && <EvidenceDrawer result={result} selectedId={evidenceId} onClose={()=>setEvidenceId(null)}/>}
  </div>
}
