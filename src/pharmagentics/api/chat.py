"""Read-only, role-shaped question answering. No model, arbitrary SQL or browser-supplied facts.

This complements the investigation/review workspaces. It never generates or publishes a brief.
"""
from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field

from . import forecast_store, rbac, service, store, views
from .schemas import Territory
from ..tools import Registry, queries as q

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])
Intent = Literal["metric", "share", "change", "health", "forecast", "drivers", "residual", "verification", "next", "summary", "review", "evidence", "definition"]


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    lane: Literal["briefing", "forecast"]
    question: str = Field(min_length=3, max_length=1000)
    brand_id: Literal["BXA"] = "BXA"
    territory_id: Territory = "NATIONAL"
    week_start: date | None = None
    window_weeks: int = Field(default=1, ge=1, le=52)
    record_id: str | None = Field(default=None, pattern=r"^[bf]-[a-f0-9]{12}$")
    previous_intent: Intent | None = None
    metric: Literal['trx', 'nrx', 'nbrx'] = 'trx'


def _role(p: rbac.Principal, lane: str) -> rbac.Role:
    role = p.role(lane)
    if role is None or not rbac.lane_available(lane):
        raise HTTPException(403, "Your account has no access to this workspace.")
    rbac.allow(role, "read")
    return role


def _records(lane: str, role: rbac.Role) -> list[dict]:
    if lane == "briefing":
        version = service.current_data_version()
        if "run" not in role.actions:
            return store.approved(version)
        records = [store.get_brief(key.removeprefix("briefs/").removesuffix(".json"))
                   for key in store.backend().keys("briefs/")]
        return [r for r in records if r and r["result"].get("data_version") == version]
    return [r for r in forecast_store.all_runs()
            if "run" in role.actions or r["review_status"] != "not_submitted"]


def _summary(lane: str, record: dict) -> dict:
    source = record["result"] if lane == "briefing" else record["request"]
    return {"id": record["brief_id"] if lane == "briefing" else record["run_id"],
            "territory_id": source["territory_id"], "week_start": str(source["week_start"]),
            "window_weeks": source.get("window_weeks", 1), "review_status": record["review_status"]}


def _context(lane: str, role: rbac.Role) -> dict:
    records = sorted((_summary(lane, r) for r in _records(lane, role)),
                     key=lambda r: (r["week_start"], r["id"]), reverse=True)
    analyst = "run" in role.actions
    if analyst:
        release = service.release_context()
        weeks = [w.isoformat() for w in release.available_weeks]
        territories = ["NATIONAL", *release.territory_ids]
    else:
        weeks = sorted({r["week_start"] for r in records})
        territories = sorted({r["territory_id"] for r in records})
    return {"lane": lane, "view": role.views[0], "live_metrics": analyst,
            "weeks": weeks, "territories": territories, "latest_week": weeks[-1] if weeks else None,
            "records": records, "engine": "governed_queries"}


def _intent(text: str, previous: str | None) -> str | None:
    text = text.lower()
    if re.search(r"\b(ignore|override|system prompt|execute|sql|delete|drop table|approve|publish|reject|submit|patient|prescriber|dosage|weather)\b", text):
        return None
    terms = [
        ("definition", r"^(?:what (?:is|are|does)|define|meaning of)\s+(?:trx|nrx|nbrx|market share)(?:\s+(?:mean|stand for))?[?.!\s]*$"),
        ("health", r"\b(data quality|data health|feed|duplicate|missing|withheld|reportable|restatement|coverage)\b"),
        ("verification", r"\b(verification|verify|verified|confidence|reliab\w*)\b"),
        ("residual", r"\b(residual|unexplained|remaining gap)\b"),
        ("next", r"\b(next steps?|check next|follow.up|owner)\b"),
        ("review", r"\b(review|approval|approved|rejected|submitted|status)\b"),
        ("evidence", r"\b(evidence|source|query|trace)\b"),
        ("drivers", r"\b(why|drivers?|reason|explain|promotion|supply|inventory|payer|access|competitor|holiday)\b"),
        ("forecast", r"\b(forecast|variance|miss|gap)\b"),
        ("share", r"\b(share)\b"),
        ("change", r"\b(change|changed|versus|vs|compare|comparison|growth|decline|week.over.week)\b"),
        ("metric", r"\b(trx|nrx|nbrx|prescriptions?|volume)\b"),
        ("summary", r"\b(summary|summarize|overview|performance|brief|report|happened)\b"),
    ]
    for intent, pattern in terms:
        if re.search(pattern, text):
            return intent
    if previous and re.fullmatch(r"[\w\s?,.\-]+", text) and re.search(r"\b(what about|how about|and|previous week|last week)\b", text):
        scope_cue = re.search(r'\b\d{4}-\d{2}-\d{2}\b|\b(previous|last|next|latest) week\b|\b\d+[- ]weeks?\b', text)
        territory_cue = any(re.search(r'\b'+re.escape(label.lower()).replace(r'\-', '[- ]')+r'\b', text)
                            for label in service.TERRITORIES.values())
        if scope_cue or territory_cue or any(re.search(r'\b'+month.lower()+r'\b', text) for month in _MONTHS):
            return previous
    return None


_MONTHS = "January February March April May June July August September October November December".split()


def _scope(req: Question, default: str) -> tuple[str, date, int]:
    text = req.question
    territory, week, window = req.territory_id, req.week_start or date.fromisoformat(default), req.window_weeks
    if re.search(r'\b(today|yesterday|this month|last month|this year|last year|quarter|year.to.date|ytd)\b|\b(last|past|previous)\s+\d+\s+(days?|months?|years?)\b', text, re.I):
        raise ValueError('Choose explicit reporting weeks from the loaded release; this question uses an unsupported time period.')
    if re.search(r'\b(latest|most recent)\b', text, re.I):
        week = date.fromisoformat(default)
    hits = {tid for tid, label in service.TERRITORIES.items()
            if re.search(r"\b"+re.escape(label).replace(r"\-", r"[- ]")+r"\b", text, re.I)
            or re.search(r"\b"+re.escape(tid)+r"\b", text, re.I)}
    if re.search(r"\b(nationwide|nationally)\b", text, re.I):
        hits.add("NATIONAL")
    if len(hits) > 1:
        raise ValueError("Ask about one territory at a time, or choose National.")
    if hits:
        territory = hits.pop()
    unknown_place = re.search(r"\bin\s+([A-Za-z][A-Za-z -]*?)(?=\s+(?:for|on|during|over|in|last|this|the week)\b|[?.!,]|$)", text, re.I)
    normalize_place = lambda value: re.sub(r'[-_\s]+', ' ', value.lower()).strip().removesuffix(' please')
    known_places = {normalize_place(value) for value in [*service.TERRITORIES, *service.TERRITORIES.values()]}
    if unknown_place and normalize_place(unknown_place[1]) not in known_places:
        if normalize_place(unknown_place[1]) not in {"the report", "this report", "the brief", "this brief", "total"}:
            raise ValueError("Choose a supported territory from the scope controls.")
    dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", text)
    month_pattern = r"\b("+'|'.join(_MONTHS)+r")\s+(\d{1,2})(?:st|nd|rd|th)?[,]?\s+(\d{4})\b"
    for month, day, year in re.findall(month_pattern, text, re.I):
        dates.append(date(int(year), next(i+1 for i, m in enumerate(_MONTHS) if m.lower() == month.lower()), int(day)).isoformat())
    if len(set(dates)) > 1:
        raise ValueError("Choose a start week and analysis window instead of multiple dates.")
    if dates:
        week = date.fromisoformat(dates[0])
    if re.search(r'\b('+'|'.join(_MONTHS)+r')\b', text, re.I) and not dates:
        raise ValueError('Include the year with a written date, or choose a reporting week from the controls.')
    if match := re.search(r"\b(\d{1,2})[- ]weeks?\b", text, re.I):
        window = int(match[1])
        if not 1 <= window <= 52:
            raise ValueError("Choose an analysis window within the supported range.")
        if re.search(r"\b(last|past|previous)\s+\d+[- ]weeks?\b", text, re.I):
            week -= timedelta(weeks=window-1)
    elif re.search(r"\b(previous|last) week\b", text, re.I):
        week -= timedelta(weeks=1)
    elif re.search(r'\bnext week\b', text, re.I):
        week += timedelta(weeks=1)
    return territory, week, window


DEFINITIONS = {
    "trx": "TRx counts all synthetic prescription fills, including new prescriptions and refills.",
    "nrx": "NRx counts synthetic new prescriptions and is a subset of TRx. It does not mean new-to-brand patients.",
    "nbrx": "NBRx counts synthetic new-to-brand prescriptions and is modeled as a subset of NRx in this release.",
    "share": "Market share is the brand's reportable prescription volume divided by the reportable volume of the fictional therapy basket, for the same scope.",
}


def _metric_question(text: str, default: str = 'trx') -> str:
    for metric in ("nbrx", "nrx", "trx"):
        if re.search(r"\b"+metric+r"\b", text, re.I):
            return metric
    return default


def _live(req: Question, intent: str, territory: str, week: date, window: int) -> dict:
    release = service.release_context()
    weeks = [(week+timedelta(weeks=i)).isoformat() for i in range(window)]
    available = {w.isoformat() for w in release.available_weeks}
    if week.weekday() or any(w not in available for w in weeks):
        raise ValueError("Choose Monday reporting weeks within the loaded data release.")
    if intent == "change":
        previous = [(date.fromisoformat(w)-timedelta(weeks=window)).isoformat() for w in weeks]
        if any(w not in available for w in previous):
            raise ValueError("The comparison period is outside the loaded release.")
    else:
        previous = []
    reg = Registry(service.DB)
    try:
        scope_terrs = release.territory_ids if territory == "NATIONAL" else [territory]
        all_weeks = weeks+previous
        health = reg.rows(f"select week_start::varchar, territory_id, health_status, flag_reasons "
                          f"from reporting.v_feed_health where week_start in {q._dates(all_weeks)} "
                          f"and {q._in('territory_id', scope_terrs)}")
        states = {(w, t): (status, reason) for w, t, status, reason in health}
        good = [t for t in scope_terrs if all(states.get((w, t), ('FLAG', 'missing feed metadata'))[0] == 'PASS'
                                             for w in all_weeks)]
        bad = [(w, t, states.get((w, t), ('FLAG', 'missing feed metadata'))[1])
               for w in all_weeks for t in scope_terrs if states.get((w, t), ('FLAG', ''))[0] != 'PASS']
        preamble = f"BXA · {q.name(territory)} · {weeks[0]}" + (f" to {weeks[-1]}" if window > 1 else "")
        lines = [preamble]
        if intent == "health" or not good:
            for w, t, reasons in bad:
                reason = ', '.join(q.REASONS.get(r, r.lower().replace('_', ' ')) for r in reasons.split(';') if r)
                reg.fact('chat_feed_health', q.feed(w, t, 'flag_reasons'), week=w, territory=t)
                lines.append(f"{q.name(t)} ({w}) is not reportable: {reason}. The cut is withheld, never treated as zero demand.")
            if not bad:
                reg.fact('chat_feed_health', f"select count(*) from reporting.v_feed_health where week_start in {q._dates(weeks)} "
                         f"and {q._in('territory_id', scope_terrs)} and health_status <> 'PASS'")
                lines.append("All selected cuts pass the feed-health gate.")
            if not good:
                lines.append("No metric is reported for this scope because no territory passes throughout the selected period.")
        if good and intent != 'health':
            if territory == 'NATIONAL':
                count = reg.claim('chat_coverage', f"select count(distinct territory_id) from reporting.v_feed_health "
                                  f"where week_start in {q._dates(weeks)} and {q._in('territory_id', good)}")
                total = reg.claim('chat_coverage', 'select count(*) from raw.dim_territory')
                lines.append(f"Coverage: {count} of {total} territories, reportable throughout the selected and comparison periods.")
                if bad:
                    lines.append("Withheld territories: "+', '.join(q.name(t) for t in scope_terrs if t not in good)+'.')
            metric = _metric_question(req.question, req.metric)
            current_sql = q.trx_sum(weeks, terrs=good, col=metric)
            if intent == 'share':
                sql = q.share(weeks, 'BXA', terrs=good)
                if reg.scalar(sql) is None:
                    lines.append('Market share is unavailable because the basket has no reportable volume.')
                else:
                    lines.append(f"BXA market share: {reg.claim('chat_market_share', sql, 'pct1')} of the fictional therapy basket.")
            elif intent == 'forecast':
                where = f"from {q.FVA} where product_id = 'BXA' and week_start in {q._dates(weeks)} and {q._in('territory_id', good)}"
                count = reg.scalar('select count(*) '+where)
                if count != len(weeks)*len(good):
                    lines.append('A complete forecast is unavailable for the reportable scope; no variance was calculated.')
                else:
                    fsql = 'select sum(forecast_trx) '+where
                    actual_sql = q.trx_sum(weeks, terrs=good)
                    lines.append(f"Actual TRx: {reg.claim('chat_actual', actual_sql)}. Forecast TRx: {reg.claim('chat_forecast', fsql)}.")
                    lines.append(f"Variance (actual minus forecast): {reg.claim('chat_variance', f'select ({actual_sql}) - ({fsql})')} TRx.")
            else:
                label = {'trx': 'TRx', 'nrx': 'NRx', 'nbrx': 'NBRx'}[metric]
                lines.append(f"{label}: {reg.claim('chat_metric', current_sql)} synthetic prescriptions.")
                if intent == 'change':
                    prior_sql = q.trx_sum(previous, terrs=good, col=metric)
                    lines.append(f"Previous comparable period ({previous[0]} to {previous[-1]}): {reg.claim('chat_metric', prior_sql)}.")
                    change_sql = q.pct_change(current_sql, prior_sql)
                    change = reg.scalar(change_sql)
                    if change is None:
                        lines.append('A percentage change cannot be calculated from a zero comparison value.')
                    else:
                        direction = 'up' if change > 0 else 'down' if change < 0 else 'unchanged at'
                        lines.append(f"Change: {direction} {reg.claim('chat_change', change_sql, 'pct1')} on the same reportable territories.")
        answer, citations = reg.render_cited('\n\n'.join(lines))
        return {'answer': answer, 'claims': reg.claims, 'evidence': reg.evidence,
                'citations': citations, 'data_version': reg.data_version}
    finally:
        reg.close()


def _from_report(lane: str, record: dict, role: rbac.Role, intent: str, metric: str) -> dict:
    analyst = 'run' in role.actions
    if lane == 'briefing':
        shaped = views.analyst(record) if analyst else views.leadership(record)
        original = shaped['answer'] if analyst else shaped['summary']
        answer = original
        if intent == 'review':
            answer = 'Review status: '+record['review_status'].replace('_', ' ')+'.'
        elif intent == 'health':
            paragraphs = [p for p in answer.splitlines() if re.search(r'\b(data health|withheld|not reportable|restated|data artifact)\b', p, re.I)]
            answer = '\n'.join(paragraphs) if paragraphs else 'This saved summary does not include a data-health statement. Ask the analyst to review its feed-health checks.'
        elif intent == 'next':
            paragraphs = [p for p in answer.splitlines() if re.search(r'\b(next|involve|investigate next)\b', p, re.I)]
            answer = '\n'.join(paragraphs) if paragraphs else 'This saved brief does not name a next check. Open its summary for context.'
        elif intent == 'evidence':
            answer = ('Open the numbered sources below to inspect the stored queries and pinned data version.' if analyst
                      else 'Source queries and analyst evidence are available only to the Commercial Analyst. You can ask for the approved summary.')
        elif intent not in {'summary', 'drivers'}:
            return {'status': 'unsupported', 'answer': 'This saved Briefing contains a reviewed narrative. Ask for its summary, explanations, next checks or review status.'}
        out = {'answer': answer}
        if analyst:
            # Preserve the stored claim identity, even when different metrics have equal values.
            spans, source_pos, target_pos = [], 0, 0
            for value in answer.splitlines(keepends=True):
                line = value.rstrip('\r\n')
                found = original.find(line, source_pos) if line else -1
                if found >= 0:
                    for span in shaped.get('citations') or []:
                        if found <= span['start'] < span['end'] <= found+len(line):
                            spans.append({'start': target_pos+span['start']-found,
                                          'end': target_pos+span['end']-found, 'claim': span['claim']})
                    source_pos = found+len(line)
                target_pos += len(value)
            out.update(claims=shaped['claims'], evidence=shaped['evidence'], citations=spans,
                       data_version=shaped['data_version'])
        return out
    shaped = views.forecast_record(record, role.views[0])
    report = shaped['report']
    if intent == 'metric' and metric != 'trx':
        return {'status': 'unsupported', 'answer': 'This Forecast report covers TRx only. No NRx or NBRx figure is supplied by this report.'}
    def number(value):
        return 'unavailable' if value is None else f'{value:,.1f}'.removesuffix('.0')
    headline = report['headline']
    caveats = report.get('caveats', [])
    if intent == 'review':
        answer = 'Review status: '+record['review_status'].replace('_', ' ')+'.'
    elif intent == 'health':
        answer = ('Attribution is paused in this saved report; review the recorded caveats before interpreting its actuals.'
                  if report.get('abstained') else 'This saved report did not pause attribution. Review its recorded caveats and verification verdict before using its figures.')
    elif intent == 'drivers':
        drivers = report['drivers']
        answer = '\n'.join(f"{d['driver'].replace('_', ' ')}: {number(d['impact_trx'])} TRx; confidence {d['confidence']}." for d in drivers)
        if not drivers:
            answer = 'No drivers were assigned in this saved report.'
    elif intent == 'residual':
        answer = f"Unexplained residual: {number(report['residual_trx'])} TRx. It remains unexplained rather than being assigned to a driver."
    elif intent == 'next':
        answer = '\n'.join(f"{c['question']} {c['why']} Owner: {c['owner']}." for c in report.get('what_to_check', [])) or 'No next checks were recorded.'
    elif intent == 'verification':
        answer = 'Verification verdict: '+report.get('verification', {}).get('verdict', 'unavailable')+'.'
    elif intent == 'evidence':
        answer = ('Open this report in the Forecast workspace for its analyst trace.' if analyst else
                  'Evidence and traces are restricted to the analyst. You can ask about the executive summary, drivers, residual or caveats.')
    elif intent in {'summary', 'forecast', 'metric', 'change'}:
        answer = f"{headline}\nActual TRx: {number(report['actual_trx'])}. Forecast TRx: {number(report['forecast_trx'])}. Variance: {number(report['variance_trx'])} TRx."
    else:
        answer = 'This saved Forecast report does not answer that metric. Ask about its summary, variance, drivers, residual, verification or next checks.'
    if report.get('abstained'):
        answer += '\nAttribution is paused because the actual data is provisional or the evidence is insufficient.'
    if caveats:
        answer += '\n\nCaveats: '+' '.join(caveats)
    out = {'answer': answer}
    if analyst:
        out.update(data_version=(shaped.get('pin') or {}).get('data_version'))
    return out


def _answer(req: Question, p: rbac.Principal, role: rbac.Role) -> dict:
    records = _records(req.lane, role)
    record = next((r for r in records if _summary(req.lane, r)['id'] == req.record_id), None)
    if req.record_id and record is None:
        raise HTTPException(404, 'No accessible report with that identifier.')
    context = _context(req.lane, role)
    default = context['latest_week']
    metric = _metric_question(req.question, req.metric)
    base = {'lane': req.lane, 'view': role.views[0], 'engine': 'governed_queries', 'status': 'answered', 'metric': metric}
    intent = _intent(req.question, req.previous_intent)
    if re.search(r'\b(BX[B-Z]|Metacora|Lumina)\b', req.question, re.I):
        intent = None
    named_metric = re.search(r"\b([a-z][a-z0-9-]*)(?:['’]s)?\s+(?:trx|nrx|nbrx)\b", req.question, re.I)
    if named_metric and named_metric[1].lower() not in {'bxa', 'cardiovela', 'total', 'weekly', 'actual', 'forecast',
            'reported', 'reportable', 'the', 'in', 'and', 'our', 'current', 'brand', 'synthetic', 'is', 'was', 'did',
            'many', 'show', 'tell', 'calculate', 'compare', 'get', 'report', 'about', 'more', 'were', 'are', 'has', 'have'}:
        intent = None
    if not intent:
        return {**base, 'status': 'unsupported', 'intent': None,
                'answer': 'I can answer BXA commercial questions about prescription metrics, share, changes, feed health and saved report explanations. Choose a scope or report and ask one of those questions. I cannot perform actions, run supplied SQL, or answer clinical and unrelated questions.'}
    base['intent'] = intent
    if intent == 'definition':
        metric = 'share' if 'share' in req.question.lower() else _metric_question(req.question)
        return {**base, 'answer': DEFINITIONS[metric]}
    if not default:
        return {**base, 'status': 'needs_report', 'answer': 'There are no reports available to your role yet. Ask an analyst to complete the existing review/submission workflow first.'}
    territory, week, window = _scope(req, default)
    scope = {'territory_id': territory, 'week_start': week.isoformat(), 'window_weeks': window}
    base['scope'] = scope
    analyst = 'run' in role.actions
    if record:
        saved = _summary(req.lane, record)
        if any(scope[k] != saved[k] for k in scope):
            return {**base, 'status': 'needs_report', 'answer': 'The selected report covers a different scope. Select a matching report, or choose live metrics if your role allows them.'}
        return {**base, 'record_id': saved['id'], 'review_status': record['review_status'],
                **_from_report(req.lane, record, role, intent, metric)}
    if not analyst or intent in {'drivers', 'residual', 'verification', 'next', 'summary', 'review', 'evidence'}:
        return {**base, 'status': 'needs_report', 'answer': 'Select an accessible saved report to answer this question. New investigations and review decisions remain in the Briefing or Forecast workspace.'}
    return {**base, **_live(req, intent, territory, week, window)}


@router.get('/context')
async def context(lane: Literal['briefing', 'forecast'], response: Response,
                  p: rbac.Principal = Depends(rbac.require_user)) -> dict:
    response.headers['Cache-Control'] = 'no-store'
    role = _role(p, lane)
    try:
        return await run_in_threadpool(_context, lane, role)
    except service.MissingDatabase as exc:
        raise HTTPException(503, str(exc)) from exc


@router.post('/query')
async def ask(req: Question, response: Response, p: rbac.Principal = Depends(rbac.require_user)) -> dict:
    response.headers['Cache-Control'] = 'no-store'
    role = _role(p, req.lane)
    try:
        result = await run_in_threadpool(_answer, req, p, role)
    except service.MissingDatabase as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except HTTPException:
        raise
    except Exception:
        log.exception('Question answering failed')
        raise HTTPException(500, 'The data could not be queried. No answer was substituted.') from None
    store.record_event('chat_question', user=rbac.pseudonym(p.sub), role=role.name, lane=req.lane,
                       intent=result.get('intent'), status=result['status'], record_id=req.record_id)
    return result
