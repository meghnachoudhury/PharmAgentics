"""Stage 1 to 3 steps of the spine, plus the story head and the competitor status, as plain functions.

The Briefing scripted baseline calls them in a fixed order; the MCP server (`pharmagentics.mcp`) exposes
them as tools an agent calls in the order it chooses. Same code in both, so the scripted baseline stays
the manager-off ablation (Briefing Architecture §9). The Forecast lane may reuse the period, feed health,
restatements and competitor status. Every number in returned text is a claim token `{cN}` filled by code.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from . import queries as q
from .checks import access_events, launch_date
from .registry import Registry
from .window import parse

MATERIAL_CHANGE, MATERIAL_GAP, NOISE_Z = 0.10, 0.08, 2.5


def word(change: float) -> str:
    return "up" if change > 0.5 else "down" if change < -0.5 else "flat"


def _mean(xs):
    return sum(xs) / len(xs) if xs else None


@dataclass
class Period:
    """What one run is about, resolved by code before any interpretation (stages 1 to 3 bookkeeping)."""

    question: str
    first: str  # first week in the release
    latest: str  # latest closed week
    requested: list[str]  # weeks the question asks about, inside the release
    baseline: list[str]  # the weeks before, for comparison
    weeks: list[str] = field(default_factory=list)  # requested weeks minus calendar weeks when those are a minority
    focus: str | None = None  # territory the question names, if any
    note: str | None = None  # how the period was chosen, when the question gave none
    status: dict = field(default_factory=dict)  # (week, territory) -> (health_status, flag_reasons)
    terrs: list[str] = field(default_factory=list)  # territories with feed metadata in these weeks
    ok: list[str] = field(default_factory=list)  # like for like: every week of period and baseline passes the gate
    calendar: list = field(default_factory=list)  # calendar rows when the period is in calendar mode
    calendar_note: str | None = None  # set when calendar weeks were left out of the stories


def resolve(reg: Registry, question: str) -> Period:
    first, latest = reg.rows("select min(week_start)::varchar, max(week_start)::varchar from raw.calendar")[0]
    ask = parse(question, first, latest)
    W = ask["weeks"]
    p = Period(question=question, first=first, latest=latest, requested=W, baseline=[], focus=ask["territory"], note=ask["note"])
    if not W:
        return p
    n_b = 4 if len(W) == 1 else min(len(W), 13)
    p.baseline = [w for w in (q.shift(W[0], -i) for i in range(n_b, 0, -1)) if w >= first]
    weeks = sorted(set(W) | set(p.baseline))
    health = reg.rows(f"select week_start::varchar, territory_id, health_status, flag_reasons "
                      f"from reporting.v_feed_health where week_start in {q._dates(weeks)}")
    p.status = {(w, t): (h, r) for w, t, h, r in health}
    p.terrs = sorted({t for _, t in p.status})
    p.ok = [t for t in p.terrs if all(p.status.get((w, t), ("FLAG", ""))[0] == "PASS" for w in weeks)]
    cal_rows = reg.rows(f"select week_start::varchar, holiday_name, business_days, plan_year_reset from raw.calendar "
                        f"where week_start in {q._dates(W)} and (holiday_flag = 1 or plan_year_reset = 1)")
    cal_weeks = {r[0] for r in cal_rows}
    # Calendar mode when calendar weeks make up half or more of the period; otherwise screen the other weeks.
    p.calendar = cal_rows if len(cal_weeks) * 2 >= len(W) else []
    p.weeks = list(W)
    if cal_weeks and not p.calendar:
        p.weeks = [w for w in W if w not in cal_weeks]
        p.calendar_note = "Calendar weeks in this period are left out of the stories below, because lower volume there is expected."
    return p


def describe(p: Period) -> str:
    W = p.requested
    return "week of " + W[0] if len(W) == 1 else "weeks " + W[0] + " to " + W[-1]


def outside_release(p: Period) -> str:
    return f"That period is outside the release, which runs from {p.first} to {p.latest}. Nothing was run."


# Stage 2: validation gate --------------------------------------------------------------------------

def data_health(reg: Registry, p: Period) -> str:
    W, terrs, status = p.requested, p.terrs, p.status
    flagged = sorted((w, t, status[(w, t)][1]) for w in W for t in terrs if status.get((w, t), ("PASS", ""))[0] == "FLAG")
    if len(W) == 1:
        n_ok = reg.claim("validate_feed", f"select count(*) from reporting.v_feed_health where week_start = DATE '{W[0]}' and health_status = 'PASS'", "int", week=W[0])
        total = reg.claim("validate_feed", f"select count(*) from reporting.v_feed_health where week_start = DATE '{W[0]}'", "int", week=W[0])
        head = f"Data health: {n_ok} of {total} territories pass the feed gate for {W[0]}."
    else:
        n_bad = reg.claim("validate_feed", f"select count(*) from reporting.v_feed_health where health_status = 'FLAG' and week_start in {q._dates(W)}", "int")
        head = f"Data health: {n_bad} territory-weeks are withheld across these weeks."
    if not flagged:
        return head + " No cut is withheld."
    lines = [head + " Withheld cuts are left out of every figure below and never read as zero demand:"]
    for w, t, reasons in flagged[:5 if len(W) > 1 else 8]:
        names = ", ".join(q.REASONS.get(r, r.lower()) for r in reasons.split(";") if r)
        detail = []
        if "DUPLICATE_RX_KEYS" in reasons or "MISSING_RX_KEYS" in reasons or "ROW_COUNT_MISMATCH" in reasons:
            obs = reg.claim("validate_feed", q.feed(w, t, "observed_rows"), "int", week=w, territory=t)
            exp = reg.claim("validate_feed", q.feed(w, t, "expected_key_count"), "int", week=w, territory=t)
            detail.append(f"{obs} rows against {exp} expected")
        if "DUPLICATE_RX_KEYS" in reasons:
            detail.append(f"{reg.claim('validate_feed', q.feed(w, t, 'duplicate_key_count'), 'int', week=w, territory=t)} duplicate keys")
        if "MISSING_RX_KEYS" in reasons:
            detail.append(f"{reg.claim('validate_feed', q.feed(w, t, 'missing_key_count'), 'int', week=w, territory=t)} missing keys")
        if "LOW_OR_INVALID_COVERAGE" in reasons:
            detail.append(f"panel coverage {reg.claim('validate_feed', q.feed(w, t, 'panel_coverage_ratio'), 'dec3', week=w, territory=t)}")
        if "LATE_OR_UNKNOWN_DELIVERY" in reasons:
            detail.append(f"{reg.claim('validate_feed', q.feed(w, t, 'actual_lag_days'), 'dec2', week=w, territory=t)} days after week end")
        lines.append(f"- {q.name(t)}, week of {w}: not reportable ({names})" + (f"; {', '.join(detail)}." if detail else "."))
    if len(flagged) > 5 and len(W) > 1:
        lines.append("- More withheld cuts exist; see the evidence list.")
    return "\n".join(lines)


def restatements(reg: Registry, p: Period) -> list[str]:
    W = p.requested
    rows = reg.rows(
        "select week_start::varchar, territory_id, min(revised_at)::varchar, any_value(revision_reason) from raw.restatement_log "
        f"where product_id = 'BXA' and (week_start in {q._dates(W)} or revised_at between DATE '{W[0]}' and DATE '{q.shift(W[-1], 1)}') "
        "group by 1, 2 order by 1, 2")
    out = []
    for w, t, when, reason in rows[:3]:
        base = f"from raw.restatement_log where product_id = 'BXA' and week_start = DATE '{w}' and territory_id = '{t}'"
        old = reg.claim("get_restatement", f"select sum(trx_prior) {base}", "int", week=w, territory=t)
        new = reg.claim("get_restatement", f"select sum(trx_revised) {base}", "int", week=w, territory=t)
        out.append(f"Restated: {q.name(t)} BXA TRx for the week of {w} was {old} when first reported and is now {new} "
                   f"(restated {when}; reason: {reason.lower().replace('_', ' ')}). Quote the new value with this note.")
    return out


# Stage 3: competitive intelligence ----------------------------------------------------------------

def kpis(reg: Registry, p: Period) -> list[str]:
    W, B, ok, terrs, calendar = p.weeks, p.baseline, p.ok, p.terrs, p.calendar
    if not ok:
        return ["KPIs: no territory passes the feed gate in every one of these weeks, so no like-for-like national figure is given."]
    cur, base = q.mean_weekly(W, terrs=ok), q.mean_weekly(B, terrs=ok) if B else None
    n = reg.claim("get_metric", f"select count(distinct territory_id) from {q.RX} where week_start in {q._dates(W)} and {q._in('territory_id', ok)}", "int")
    avg = reg.claim("get_metric", cur, "int", scope="like-for-like national")
    total = reg.claim("get_metric", "select count(*) from raw.dim_territory", "int")
    lines = []
    if base:
        change = reg.scalar(q.pct_change(cur, base)) or 0
        pct = reg.claim("get_metric", q.pct_change(cur, base), "pct1", scope="like-for-like national")
        lines.append(f"KPIs: BXA TRx averaged {avg} a week across {n} of {total} territories (like for like), "
                     f"{word(change)} {pct} against the weeks before.")
        # headline total over every reportable cut, which a withheld cut distorts
        all_cur, all_base = q.mean_weekly(W), q.mean_weekly(B)
        naive = reg.scalar(q.pct_change(all_cur, all_base)) or 0
        if len(ok) < len(terrs) and abs(naive - change) >= 5:
            p2 = reg.claim("get_metric", q.pct_change(all_cur, all_base), "pct1", scope="headline total of reportable cuts")
            lines.append(f"The headline total of reportable cuts is {word(naive)} {p2}, but that move comes mostly from withheld cuts, so it is a data artifact, not a business change.")
    if len(W) == 1 and B:
        lines += week_over_week(reg, p)
    if calendar:
        for w, holiday, bd, reset in calendar[:3]:
            days = reg.claim("lookup_calendar", q.calendar(w, "business_days"), "int", week=w)
            tag = "plan-year reset" if reset and holiday == "NONE" else holiday.lower().replace("_", " ")
            lines.append(f"Calendar effect: the week of {w} is {tag} with {days} business days, so a lower volume is expected.")
        ly_cur, ly_base = q.mean_weekly([q.shift(w, -52) for w in W], terrs=ok), q.mean_weekly([q.shift(w, -52) for w in B], terrs=ok) if B else None
        if ly_base:
            ly = reg.scalar(q.pct_change(ly_cur, ly_base)) or 0
            lines.append(f"The same weeks a year earlier were {word(ly)} {reg.claim('get_metric', q.pct_change(ly_cur, ly_base), 'pct1', scope='same weeks last year')}. This is a calendar effect, not a business event.")
    return lines


def week_over_week(reg: Registry, p: Period) -> list[str]:
    """A one-week period against the week before (§5.3): every reportable cut, then like for like on the
    territories that report both weeks, so a withheld cut cannot pass for a drop in demand."""
    w, prev = p.weeks[0], p.baseline[-1]

    def passes(week, t):
        return p.status.get((week, t), ("FLAG", ""))[0] == "PASS"

    both = [t for t in p.terrs if passes(w, t) and passes(prev, t)]
    now_all, prev_all = q.trx_sum([w]), q.trx_sum([prev])
    change = reg.scalar(q.pct_change(now_all, prev_all)) or 0
    lines = [f"Week over week, summed over reportable cuts: BXA TRx is {reg.claim('get_metric', now_all, 'int', week=w)} "
             f"against {reg.claim('get_metric', prev_all, 'int', week=prev)} the week before "
             f"({word(change)} {reg.claim('get_metric', q.pct_change(now_all, prev_all), 'pct1', scope='week over week, reportable cuts')})."]
    if both and len(both) < len(p.terrs):
        now_b, prev_b = q.trx_sum([w], terrs=both), q.trx_sum([prev], terrs=both)
        ch = reg.scalar(q.pct_change(now_b, prev_b)) or 0
        n = reg.claim("get_metric", f"select count(distinct territory_id) from {q.RX} where week_start = DATE '{w}' "
                      f"and {q._in('territory_id', both)}", "int", scope="territories reporting both weeks")
        lines.append(f"On the {n} territories that report both weeks, BXA TRx went from "
                     f"{reg.claim('get_metric', prev_b, 'int', week=prev, scope='like for like')} to "
                     f"{reg.claim('get_metric', now_b, 'int', week=w, scope='like for like')} "
                     f"({word(ch)} {reg.claim('get_metric', q.pct_change(now_b, prev_b), 'pct1', scope='week over week, like for like')}).")
    return lines


def _series(reg):
    rows = reg.rows(f"select week_start::varchar, territory_id, sum(trx) from {q.RX} where product_id = 'BXA' group by 1, 2")
    s: dict[str, dict[str, float]] = {}
    for w, t, x in rows:
        s.setdefault(t, {})[w] = float(x)
    return s


def screen(reg: Registry, p: Period):
    """Territories whose change is beyond their own normal noise and beyond their peers' change."""
    W, B, ok, focus = p.weeks, p.baseline, p.ok, p.focus
    series = _series(reg)
    flagged_cal = {w for (w,) in reg.rows("select week_start::varchar from raw.calendar where holiday_flag = 1 or plan_year_reset = 1")}
    found, quiet = [], []
    for t in ok:
        if not B:
            continue
        x, b = _mean([series[t][w] for w in W]), _mean([series[t][w] for w in B])
        peers_x = sum(_mean([series[o][w] for w in W]) for o in ok if o != t)
        peers_b = sum(_mean([series[o][w] for w in B]) for o in ok if o != t)
        change, gap = x / b - 1, x / b - peers_x / peers_b if peers_b else 0
        hist = sorted(w for w in series[t] if w < W[0] and w not in flagged_cal)[-60:]
        devs = [series[t][w] / _mean([series[t][p] for p in hist[max(0, i - 4):i]]) - 1 for i, w in enumerate(hist) if i >= 4]
        sigma = max(statistics.pstdev(devs), 0.04) if len(devs) > 8 else 0.08
        material = abs(change) >= max(MATERIAL_CHANGE, NOISE_Z * sigma / min(len(W), 3) ** 0.5) and abs(gap) >= MATERIAL_GAP
        if material or t == focus:
            found.append({"territory": t, "kind": "territory", "impact": abs(x - b), "change": change})
        else:
            quiet.append(t)
    if not focus or focus == "NATIONAL":
        for e in access_events(reg, None, W):
            t = e["territory"]
            if t in ok and not any(s["territory"] == t for s in found) and B:
                plan_change = reg.scalar(q.pct_change(q.mean_weekly(W, plan=e["plan"]), q.mean_weekly(B, plan=e["plan"])))
                if plan_change is not None and abs(plan_change) >= 15:
                    found.append({"territory": t, "kind": "plan", "impact": abs(reg.scalar(q.mean_weekly(W, plan=e["plan"])) - reg.scalar(q.mean_weekly(B, plan=e["plan"]))), "plan": e["plan"]})
                    quiet = [x for x in quiet if x != t]
    found.sort(key=lambda s: -s["impact"])
    return found, quiet


def dropped_count(reg: Registry, p: Period, dropped: list[str]) -> str:
    return reg.claim("detect_changes", f"select count(distinct territory_id) from {q.RX} where week_start in {q._dates(p.weeks)} "
                     f"and {q._in('territory_id', dropped)}", "int", scope="territories with no material change")


# Stage 4 helpers: the story head and the competitor status -----------------------------------------

def territory_change(reg: Registry, p: Period, t: str) -> str:
    W, B = p.weeks, p.baseline
    x, b = q.mean_weekly(W, terrs=[t]), q.mean_weekly(B, terrs=[t])
    peers = [o for o in p.ok if o != t]
    px, pb = q.mean_weekly(W, terrs=peers), q.mean_weekly(B, terrs=peers)
    change = reg.scalar(q.pct_change(x, b)) or 0
    peer = reg.scalar(q.pct_change(px, pb)) or 0
    return (f"{q.name(t)}. BXA TRx averaged {reg.claim('get_metric', x, 'int', territory=t)} a week against "
            f"{reg.claim('get_metric', b, 'int', territory=t)} before ({word(change)} {reg.claim('get_metric', q.pct_change(x, b), 'pct1', territory=t)}), "
            f"while the other territories were {word(peer)} {reg.claim('get_metric', q.pct_change(px, pb), 'pct1', scope='other territories')}.")


def competitor_status(reg: Registry, p: Period, lead: str = "Competitor Metacora") -> str | None:
    """Metacora (BXE) as a continuing story: weeks since launch, direction, and the basket shares."""
    W = p.weeks
    launched = launch_date(reg)
    if launched is None or launched > W[-1]:
        return None
    share_w = q.share(W, "BXE")
    if (reg.scalar(share_w) or 0) < 5:
        return None
    pre = [q.shift(launched, -i) for i in range(4, 0, -1)]
    since = reg.claim("compare_competitors", f"select datediff('week', DATE '{launched}', week_start) from raw.calendar "
                      f"where week_start = DATE '{W[-1]}'", "int")
    earlier = [q.shift(w, -8) for w in W]
    trend = (reg.scalar(share_w) or 0) - (reg.scalar(q.share(earlier, "BXE")) or 0)
    direction = "still growing" if trend > 1 else "now flat" if trend > -1 else "declining"
    bxe = reg.claim("compare_competitors", share_w, "pct1", product="BXE")
    bxa = reg.claim("compare_competitors", q.share(W, "BXA"), "pct1", product="BXA")
    bxa_pre = reg.claim("compare_competitors", q.share(pre, "BXA"), "pct1", product="BXA", weeks="before launch")
    return (f"{lead} (launched {launched}). This is a continuing story, week {since} since launch, {direction}. "
            f"Metacora held {bxe} of the four-brand basket and BXA held {bxa}, against {bxa_pre} for BXA in the four weeks before launch. "
            f"Confidence: Medium. The share loss is measured; its effect on volume is not separated from other drivers. Next: involve marketing and sales.")
