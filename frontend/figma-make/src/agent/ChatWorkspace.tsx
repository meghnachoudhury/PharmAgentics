import {useEffect, useRef, useState, type ReactNode} from 'react'
import {askQuestion, getChatContext, type ChatAnswer, type ChatContext, type ChatIntent, type ChatLane, type ChatScope} from './chatApi'
import {NotSignedIn} from './briefingApi'
import {Icon} from './primitives'

const label = (value: string) => value.toLowerCase().split('_').map(v=>v[0]?.toUpperCase()+v.slice(1)).join(' ')
const errorText = (e: unknown) => e instanceof Error ? e.message : String(e)
type Turn = {question: string; answer?: ChatAnswer; error?: string}

function Answer({value}: {value: ChatAnswer}) {
  const [source,setSource] = useState<string | null>(null)
  const parts: ReactNode[] = []
  let pos = 0
  for (const [i, citation] of [...(value.citations ?? [])].sort((a,b)=>a.start-b.start).entries()) {
    const claim = value.claims?.[citation.claim]
    if (!claim || citation.start < pos || value.answer.slice(citation.start,citation.end) !== claim.value) continue
    parts.push(value.answer.slice(pos,citation.start))
    parts.push(<button key={i} type="button" onClick={()=>setSource(claim.evidence_id)} aria-label={`Open source for ${claim.value}`} className="font-medium underline decoration-slate-400 decoration-dotted underline-offset-4 hover:bg-agentbg">{claim.value}<sup className="ml-0.5 text-[9px] text-agentdeep">{claim.evidence_id}</sup></button>)
    pos = citation.end
  }
  parts.push(value.answer.slice(pos))
  const selected = value.evidence?.find(e=>e.id===source)
  return <>
    <div className="whitespace-pre-wrap break-words text-sm leading-7">{parts}</div>
    {!!value.evidence?.length && <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-rule pt-3">
      <span className="text-xs text-muted">Sources:</span>{value.evidence.map(ev=><button key={ev.id} onClick={()=>setSource(ev.id)} className="rounded-lg bg-paper px-2 py-1 font-mono text-xs text-agentdeep ring-1 ring-rule">{ev.id}</button>)}
    </div>}
    {selected && <section aria-label="Answer source" className="mt-3 space-y-2 rounded-xl bg-paper p-4 text-xs ring-1 ring-rule">
      <div className="flex justify-between gap-2"><strong>{selected.id} · {selected.tool}</strong><button onClick={()=>setSource(null)} aria-label="Close answer source">Close</button></div>
      <p className="break-all">Pinned data version: {selected.data_version ?? 'Unavailable'}</p>
      <p>Result: {String(selected.result ?? 'Unavailable')}</p>
      {selected.query && <pre className="overflow-x-auto whitespace-pre-wrap break-words font-mono leading-5">{selected.query}</pre>}
      <pre className="overflow-x-auto whitespace-pre-wrap break-words">{JSON.stringify(selected.params, null, 2)}</pre>
    </section>}
    <p className="mt-3 text-[11px] text-muted">{value.record_id ? `Saved report ${value.record_id} · ${value.review_status?.replace(/_/g,' ')}` : 'Read-only answer from governed data'}{value.data_version ? ` · data ${value.data_version}` : ''}</p>
  </>
}

export function ChatWorkspace({lane, active}: {lane: ChatLane; active: boolean}) {
  const [context,setContext] = useState<ChatContext | null>(null)
  const [scope,setScope] = useState<ChatScope>({territory_id:'NATIONAL',week_start:'',window_weeks:1})
  const [recordId,setRecordId] = useState('')
  const [question,setQuestion] = useState('')
  const [turns,setTurns] = useState<Turn[]>([])
  const [intent,setIntent] = useState<ChatIntent | undefined>()
  const [metric,setMetric] = useState<'trx' | 'nrx' | 'nbrx'>('trx')
  const [busy,setBusy] = useState(false)
  const [loading,setLoading] = useState(false)
  const [error,setError] = useState<string | null>(null)
  const bottom = useRef<HTMLDivElement>(null)
  const load = async () => {
    setLoading(true); setError(null)
    try {
      const c = await getChatContext(lane)
      setContext(c)
      if (c.live_metrics) {
        setRecordId('')
        setScope({territory_id:'NATIONAL', week_start:c.latest_week ?? '', window_weeks:1})
      } else if (c.records[0]) {
        setRecordId(c.records[0].id)
        setScope(c.records[0])
      }
    } catch (e) {setError(errorText(e))}
    finally {setLoading(false)}
  }
  useEffect(()=>{if(active && !context && !loading && !error) void load()}, [active, context, loading, error])
  useEffect(()=>{if(active && (turns.length || busy)) bottom.current?.scrollIntoView({block:'end',behavior:'auto'})}, [turns,busy,active])
  const selectReport = (id: string) => {
    setRecordId(id);setIntent(undefined);setMetric('trx')
    const record = context?.records.find(r=>r.id===id)
    if(record) setScope(record)
  }
  const send = async (event?: React.FormEvent, suggestion?: string) => {
    event?.preventDefault()
    const text = (suggestion ?? question).trim()
    if(busy || !context || text.length<3) return
    setQuestion('');setError(null);setBusy(true)
    setTurns(v=>[...v,{question:text}])
    try {
      const answer = await askQuestion({lane,question:text, ...{territory_id:scope.territory_id,week_start:scope.week_start || undefined,window_weeks:scope.window_weeks},
        ...(recordId ? {record_id:recordId} : {}), previous_intent:intent, metric})
      if(answer.view !== context.view) throw new Error('Your access changed. Reload the workspace before continuing.')
      setTurns(v=>v.map((t,i)=>i===v.length-1 ? {...t,answer} : t))
      if(answer.scope) setScope(answer.scope)
      setIntent(answer.intent ?? undefined);setMetric(answer.metric)
    } catch(e) {
      const text = errorText(e)
      setTurns(v=>v.map((t,i)=>i===v.length-1 ? {...t,error:text} : t))
      if(e instanceof NotSignedIn) setError(text)
    } finally {setBusy(false)}
  }
  const examples = recordId ? ['Summarize this report','What are the drivers?','What should we check next?','What is the review status?'] :
    ['How many TRx prescriptions did BXA have?','What is the market share?','How did TRx change versus the previous period?','Is the feed reportable?']
  const canAsk = !!context && !loading && !busy
  return <div className="workspace-content space-y-6 py-8 sm:py-10">
    <div className="flex flex-wrap items-start justify-between gap-3"><div><span className="text-xs font-medium uppercase tracking-wider text-agentdeep">{lane==='briefing' ? 'Brand performance' : 'Forecast explanation'} · {context?.view ?? 'Your role'}</span><h2 className="mt-3 font-serif text-2xl font-medium">Ask PharmAgentics</h2><p className="mt-2 text-sm leading-6 text-muted">Ask a question, then follow up in the same conversation. Answers use governed queries or reports your role can read.</p></div>
      <button disabled={busy} onClick={()=>{setTurns([]);setQuestion('');setIntent(undefined);setMetric('trx')}} className="rounded-xl bg-sheet px-3 py-2 text-xs font-medium ring-1 ring-rule disabled:opacity-50">New conversation</button>
    </div>
    <div className="rounded-2xl bg-sheet p-4 ring-1 ring-rule">
      <div className="flex items-center justify-between gap-2"><p className="text-xs font-medium text-muted">Answer source and scope</p><button disabled={busy || loading} onClick={()=>void load()} className="text-xs text-agentdeep underline">Refresh reports</button></div>
      {loading && <p role="status" className="mt-3 text-sm text-muted">Loading your available sources…</p>}
      {context && <>
        <label className="mt-3 block text-xs text-muted">Source<select aria-label="Question source" value={recordId} onChange={e=>selectReport(e.target.value)} disabled={busy} className="mt-1 block w-full min-w-0 rounded-xl border border-rule bg-paper p-3 text-sm text-ink">
          {context.live_metrics && <option value="">Live governed metrics</option>}
          {!context.live_metrics && !context.records.length && <option value="">No accessible reports yet</option>}
          {context.records.map(r=><option key={r.id} value={r.id}>{label(r.territory_id)} · {r.week_start} · {r.review_status.replace(/_/g,' ')} · {r.id}</option>)}
        </select></label>
        {!recordId && context.live_metrics && <div className="mt-3 grid gap-3 sm:grid-cols-3">
          <label className="text-xs text-muted">Territory<select aria-label="Question territory" value={scope.territory_id} disabled={busy} onChange={e=>{setScope(s=>({...s,territory_id:e.target.value}));setIntent(undefined)}} className="mt-1 block w-full min-w-0 rounded-xl border border-rule bg-paper p-2.5 text-sm text-ink">{context.territories.map(t=><option key={t} value={t}>{label(t)}</option>)}</select></label>
          <label className="text-xs text-muted">Start week<select aria-label="Question start week" value={scope.week_start} disabled={busy} onChange={e=>{setScope(s=>({...s,week_start:e.target.value}));setIntent(undefined)}} className="mt-1 block w-full min-w-0 rounded-xl border border-rule bg-paper p-2.5 text-sm text-ink">{[...context.weeks].reverse().map(w=><option key={w} value={w}>{w}</option>)}</select></label>
          <label className="text-xs text-muted">Window<select aria-label="Question window" value={scope.window_weeks} disabled={busy} onChange={e=>{setScope(s=>({...s,window_weeks:Number(e.target.value)}));setIntent(undefined)}} className="mt-1 block w-full min-w-0 rounded-xl border border-rule bg-paper p-2.5 text-sm text-ink">{Array.from({length:52},(_,i)=>i+1).map(n=><option key={n} value={n}>{n} {n===1?'week':'weeks'}</option>)}</select></label>
        </div>}
        <p className="mt-3 text-xs leading-5 text-muted">BXA synthetic commercial data. {context.live_metrics ? 'Figures come from read-only calculations. Choose a saved report for explanations and review questions.' : lane==='briefing' ? 'Only analyst-approved briefs are available to the Brand Director.' : 'Only submitted reports are available to the Brand Manager.'} New investigations and decisions remain in the existing workspaces.</p>
      </>}
      {error && <div role="alert" className="mt-3 text-sm text-amber">{error} <button onClick={()=>void load()} className="underline">Retry</button></div>}
    </div>
    {!turns.length && <div className="rounded-2xl bg-sheet p-5 ring-1 ring-rule"><h3 className="font-serif text-xl">What would you like to know?</h3><div className="mt-4 grid gap-2 sm:grid-cols-2">{examples.map(example=><button key={example} disabled={!canAsk} onClick={()=>void send(undefined,example)} className="rounded-xl bg-paper p-3 text-left text-sm ring-1 ring-rule hover:bg-agentbg disabled:opacity-50">{example}</button>)}</div></div>}
    <div aria-label="Conversation" role="log" aria-live="polite" aria-busy={busy} className="space-y-5">
      {turns.map((turn,i)=><div key={i} className="space-y-3">
        <div className="flex justify-end"><div className="max-w-[90%] whitespace-pre-wrap break-words rounded-2xl rounded-br-md bg-navy px-5 py-3 text-sm leading-6 text-white">{turn.question}</div></div>
        {turn.answer && <article aria-label="PharmAgentics answer" className="rounded-2xl bg-sheet p-5 ring-1 ring-rule"><div className="mb-3 text-xs font-semibold text-agentdeep">PharmAgentics · Source-backed answer</div><Answer value={turn.answer}/></article>}
        {turn.error && <div role="alert" className="rounded-2xl bg-amberbg p-4 text-sm text-amber">{turn.error} Your question is kept above; you can send it again.</div>}
      </div>)}
      {busy && <p role="status" className="rounded-xl bg-sheet p-4 text-sm text-muted ring-1 ring-rule">Checking the permitted data sources…</p>}
      <div ref={bottom} className="scroll-mb-52"/>
    </div>
    <form onSubmit={event=>void send(event)} className="sticky bottom-0 rounded-2xl bg-sheet p-3 shadow-sm ring-1 ring-rule">
      <label htmlFor={`question-${lane}`} className="sr-only">Ask a brand question</label>
      <textarea id={`question-${lane}`} value={question} onChange={e=>setQuestion(e.target.value)} maxLength={1000} rows={3} placeholder={recordId ? 'Ask about this report…' : 'Ask about BXA prescriptions, share, changes or feed health…'} disabled={!context || busy} onKeyDown={e=>{if(e.key==='Enter' && !e.shiftKey && !e.nativeEvent.isComposing){e.preventDefault();void send()}}} className="block w-full resize-y rounded-xl border-0 bg-sheet p-2 text-sm leading-6 outline-none focus:ring-2 focus:ring-agent/20 disabled:opacity-50"/>
      <div className="mt-2 flex items-center justify-between gap-3"><p className="text-[11px] text-muted">Enter to send · Shift+Enter for a new line · Source-backed Q&amp;A</p><button type="submit" disabled={!canAsk || question.trim().length<3} className="flex shrink-0 items-center gap-2 rounded-xl bg-navy px-4 py-2.5 text-sm font-medium text-white disabled:bg-rule disabled:text-muted"><Icon name="send" className="h-4 w-4"/>Send</button></div>
    </form>
  </div>
}
