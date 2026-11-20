"""The investigation state and every operation on it. All arithmetic is here, in code; the rules policy and
the model agent only choose which operations to run and say why. A model never supplies a number: every
figure an answer shows is a claim token filled from one governed query (see write.py)."""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field

from pharmagentics.tools import Registry
from pharmagentics.tools.queries import REASONS, name, shift

from . import sql as S
from .scope import Scope

T = S.TERRITORIES
OWNER = {"access": "Market access", "promotion": "Sales leadership and marketing", "supply": "Supply chain and trade",
         "competitor": "Forecasting, with marketing", "calendar": "Forecasting", "residual": "Commercial analytics",
         "data": "The data vendor and commercial analytics"}
PROMO_DIP = 0.6       # rep calls below this share of the territory's median week
SUPPLY_FLOOR = 0.90   # inventory fill below this
STANDOUT_SHARE = 0.05  # a territory's excess beyond its peers, as a share of its forecast, that marks it out
STANDOUT_MIN = 100.0
PLACEBO_PARTIAL = 0.5  # pre-period excess rate above this share of the effect rate: part of the gap predates it
PLACEBO_FULL = 0.8     # above this share: the gap was already there, so the episode does not explain it
LEVELS = ["inconclusive", "low", "medium", "high"]
LOO_SHARE = 0.25       # leave-one-out: the estimate moves by more than this share when one control is dropped
RECOVERY_SHARE = 0.75  # the gap after the episode keeps more than this share of the gap during it


class Refused(Exception):
    """An operation the rules do not allow; the message is returned to the caller (often a model) verbatim."""


def no_digits(text: str, what: str = "A reason") -> str:
    text = " ".join(str(text or "").split())[:300]
    if not text:
        raise Refused(f"{what} is required.")
    if re.search(r"\d", text):
        raise Refused(f"{what} may not contain digits: numbers come only from code. Say it in words.")
    return text


@dataclass
class Episode:
    id: str
    driver: str          # access, promotion, supply, competitor, calendar
    territory: str       # a territory id, or ALL for a broad episode
    active: list[str]    # active weeks (within the release)
    label: str           # words only
    signal: dict = field(default_factory=dict)  # numbers for the investigator to read, not for the answer
    direction: int = -1  # the expected sign of the effect on TRx
    status: str = "candidate"  # candidate, accepted, rejected
    reason: str | None = None
    comparison: str | None = None

    def brief(self, weeks: list[str], contaminated: list[str] | None = None) -> dict:
        inside = [w for w in self.active if w in weeks]
        return {"id": self.id, "driver": self.driver, "territory": self.territory, "label": self.label,
                "first_active": self.active[0] if self.active else None, "last_active": self.active[-1] if self.active else None,
                "active_weeks_in_scope": len(inside), "expected_direction": "lowers TRx" if self.direction < 0 else "raises TRx",
                "signal": self.signal, "status": self.status,
                **({"controls_with_own_episode": contaminated} if contaminated is not None else {})}


@dataclass
class Comparison:
    id: str
    episode: str
    method: str
    weeks: list[str]
    controls: list[str]
    effect: float
    effect_sql: str
    stats: dict
    flags: list[str]


class Case:
    def __init__(self, reg: Registry, scope: Scope, drop_controls: list[str] | None = None):
        self.reg, self.scope = reg, scope
        # Territories the analyst asked to keep out of every control group (a follow-up such as "drop South Central").
        self.dropped = [t for t in (drop_controls or []) if t in T]
        self.first, self.latest = reg.rows("select min(week_start)::varchar, max(week_start)::varchar from raw.calendar")[0]
        self.all_weeks = [r[0] for r in reg.rows("select week_start::varchar from raw.calendar order by 1")]
        self.weeks = scope.weeks
        self.cut = scope.territory
        self.decisions: list[dict] = []
        self.comparisons: dict[str, Comparison] = {}
        self.episodes: dict[str, Episode] = {}
        self.abstained: str | None = None
        if self.dropped:
            self.decide("analyst", "drop_controls", ", ".join(name(t) for t in self.dropped),
                        "the analyst asked to keep these territories out of every control group")
        self.launch = reg.scalar("select min(effective_start)::varchar from raw.market_basket "
                                 "where launch_date not like 'BEFORE%'")
        self._gate()

    # ---- decisions log -------------------------------------------------------------------------------
    def decide(self, by: str, action: str, target: str, reason: str) -> None:
        self.decisions.append({"by": by, "action": action, "target": target, "reason": reason})

    # ---- stage 2: data gate --------------------------------------------------------------------------
    def _gate(self) -> None:
        W = self.weeks
        rows = self.reg.rows(f"select week_start::varchar, territory_id from {S.FVA} where product_id = 'BXA' "
                             f"and actual_is_provisional = 1 and week_start in {S.dates(W)} order by 1, 2") if W else []
        self.provisional = sorted({w for w, _ in rows})
        self.provisional_cuts = rows
        flags = self.reg.rows("select week_start::varchar, territory_id, flag_reasons from reporting.v_feed_health "
                              f"where health_status = 'FLAG' and week_start in {S.dates(W)} order by 1, 2") if W else []
        self.flags = [{"week": w, "territory": t, "reasons": [REASONS.get(r, r.lower()) for r in (fr or "").split(";") if r]}
                      for w, t, fr in flags]
        # A week whose actual is provisional anywhere is never attributed: comparisons need final controls too.
        self.usable = [w for w in W if w not in self.provisional]
        if self.provisional and self.usable:
            self.decide("code", "set_aside_weeks", ", ".join(self.provisional),
                        "the actual is provisional in these weeks, so they are kept out of every comparison")

    def cut_provisional(self) -> bool:
        """Whether every week of the asked cut is provisional (nothing to attribute)."""
        return not self.usable

    # ---- stage 3: variance and screen ----------------------------------------------------------------
    def variance(self, weeks=None, cut=None) -> dict:
        weeks, cut = weeks or self.usable or self.weeks, cut or self.cut
        r = self.reg
        return {"forecast": r.scalar(S.fva("forecast_trx", weeks, cut)), "actual": r.scalar(S.fva("actual_trx", weeks, cut)),
                "variance": r.scalar(S.fva("variance_trx", weeks, cut)), "pct": r.scalar(S.pct_of_forecast(weeks, cut))}

    def screen(self, weeks=None) -> list[dict]:
        """Each territory's miss, and its miss beyond what the other seven territories' rate predicts."""
        weeks = weeks or self.usable or self.weeks
        out = []
        for t in T:
            peers = [p for p in T if p != t]
            f = self.reg.scalar(S.fva("forecast_trx", weeks, t)) or 0
            v = self.reg.scalar(S.fva("variance_trx", weeks, t)) or 0
            ex = self.reg.scalar(S.excess(t, weeks, peers)) or 0
            out.append({"territory": t, "forecast": round(f), "miss": round(v), "pct": round(100 * v / f, 1) if f else None,
                        "beyond_peers": round(ex), "standout": abs(ex) >= max(STANDOUT_MIN, STANDOUT_SHARE * f),
                        "provisional_weeks": sum(1 for w, c in self.provisional_cuts if c == t)})
        return sorted(out, key=lambda r: r["miss"])

    # ---- stage 3: episode discovery (no hand-written calendar) ---------------------------------------
    def discover(self) -> list[Episode]:
        if self.episodes:
            return list(self.episodes.values())
        # Scan past the period on both sides so an episode's true start and end are known; keep the ones that touch it.
        lo = shift(self.weeks[0], -26) if self.weeks else self.first
        hi = self.latest
        found: list[Episode] = []
        found += self._promotion(lo, hi)
        found += self._supply(lo, hi)
        found += self._access(lo, hi)
        found += self._competitor(self.weeks[-1] if self.weeks else hi)
        found += self._calendar()
        keep = [e for e in found if any(w in self.weeks for w in e.active)]
        if self.cut != "NATIONAL":
            keep = [e for e in keep if e.territory in (self.cut, "ALL")]
        for i, e in enumerate(keep, 1):
            e.id = f"E{i}"
            self.episodes[e.id] = e
        return keep

    @staticmethod
    def _runs(weeks: list[str], min_len: int) -> list[list[str]]:
        runs, cur = [], []
        for w in weeks:
            if cur and w != shift(cur[-1], 1):
                runs.append(cur)
                cur = []
            cur.append(w)
        if cur:
            runs.append(cur)
        return [r for r in runs if len(r) >= min_len]

    def _promotion(self, lo: str, hi: str) -> list[Episode]:
        rows = self.reg.rows(
            "with p as (select territory_id, week_start, rep_calls_aggregated c, rep_vacancy_count_aggregated v, "
            "median(rep_calls_aggregated) over (partition by territory_id) m from raw.promo_activity where product_id = 'BXA') "
            f"select territory_id, week_start::varchar, c, v, m from p where c < {PROMO_DIP} * m "
            f"and week_start between DATE '{lo}' and DATE '{hi}' order by 1, 2")
        out = []
        for t in T:
            mine = [r for r in rows if r[0] == t]
            for run in self._runs([r[1] for r in mine], 2):
                calls = [r[2] for r in mine if r[1] in run]
                out.append(Episode("", "promotion", t, run, f"{name(t)} rep coverage lapse",
                                   {"rep_calls_per_week_during": round(statistics.mean(calls), 1),
                                    "typical_rep_calls_per_week": float(mine[0][4]),
                                    "rep_vacancies_reported": int(sum(r[3] or 0 for r in mine if r[1] in run))}))
        return out

    def _supply(self, lo: str, hi: str) -> list[Episode]:
        rows = self.reg.rows(
            "select territory_id, week_start::varchar, inventory_fill_rate, distribution_backorder_rate from raw.inventory_weekly "
            f"where product_id = 'BXA' and inventory_fill_rate < {SUPPLY_FLOOR} and week_start between DATE '{lo}' and DATE '{hi}' order by 1, 2")
        out = []
        for t in T:
            mine = [r for r in rows if r[0] == t]
            for run in self._runs([r[1] for r in mine], 1):
                out.append(Episode("", "supply", t, run, f"{name(t)} supply shortfall",
                                   {"mean_fill_rate": round(statistics.mean(r[2] for r in mine if r[1] in run), 3),
                                    "mean_backorder_rate": round(statistics.mean(r[3] for r in mine if r[1] in run), 3)}))
        return out

    def _access(self, lo: str, hi: str) -> list[Episode]:
        rows = self.reg.rows(
            "with a as (select plan_id, territory_id, payer_channel, month, covered_lives_weight w, formulary_tier t, prior_authorization pa, "
            "step_therapy st, covered c, lag(formulary_tier) over k pt, lag(prior_authorization) over k ppa, "
            "lag(step_therapy) over k pst, lag(covered) over k pc from raw.access_status_monthly where product_id = 'BXA' "
            "window k as (partition by plan_id order by month)) "
            "select plan_id, territory_id, payer_channel, month::varchar, (t > pt or pa > ppa or st > pst or c < pc) restricted, w "
            "from a where pt is not null and (t <> pt or pa <> ppa or st <> pst or c <> pc) order by 2, 4")
        lives = dict(self.reg.rows("select territory_id, sum(covered_lives_weight) from raw.dim_plan group by 1"))
        out = []
        for i, (plan, terr, channel, month, restricted, w) in enumerate(rows):
            earlier = [r for r in rows[:i] if r[0] == plan]
            if not restricted and earlier and earlier[-1][4]:
                continue  # an easing that reverses this plan's last restriction ends that episode; it is not a new one
            later = [m for p, _, _, m, _, _ in rows if p == plan and m > month]
            end = later[0] if later else None
            active = [x for x in self.all_weeks if x >= month and (end is None or x < end)]
            if not active or active[0] > hi or active[-1] < lo:
                continue
            verb = "restricted" if restricted else "eased"
            out.append(Episode("", "access", terr, active, f"{name(terr)} {channel.replace('_', ' ').title()} plan {verb} access",
                               {"plan": plan, "payer_channel": channel, "effective_month": month,
                                "reversed_month": end, "share_of_territory_covered_lives": round((w or 0) / (lives.get(terr) or 1), 3)},
                               direction=-1 if restricted else 1))
        return out

    def _competitor(self, hi: str) -> list[Episode]:
        rows = self.reg.rows("select b.product_id, p.product_name, b.effective_start::varchar from raw.market_basket b "
                             "join raw.dim_product p using (product_id) where b.launch_date not like 'BEFORE%' "
                             f"and b.effective_start <= DATE '{hi}'")
        out = []
        for pid, pname, start in rows:
            active = [w for w in self.all_weeks if w >= start]
            pre = [shift(start, -i) for i in range(4, 0, -1)]
            out.append(Episode("", "competitor", "ALL", active, f"{pname} launch, in every territory",
                               {"product": pid, "launched": start,
                                "bxa_share_before_launch_pct": round(self.reg.scalar(S.bxa_share(pre, T)) or 0, 1),
                                "competitor_share_in_scope_pct": round(self.reg.scalar(
                                    S.product_share(self.usable or self.weeks, pid, T)) or 0, 1)}))
        return out

    def _calendar(self) -> list[Episode]:
        rows = self.reg.rows(f"select week_start::varchar, holiday_name from raw.calendar where holiday_flag = 1 "
                             f"and week_start in {S.dates(self.weeks)}") if self.weeks else []
        return [Episode("", "calendar", "ALL", [w], f"{(h or 'holiday').replace('_', ' ').title()} (holiday)", {"holiday": h})
                for w, h in rows]

    # ---- stage 4: comparisons ------------------------------------------------------------------------
    def contaminated(self, ep: Episode, weeks: list[str]) -> list[str]:
        """Control territories with an episode of their own in these weeks."""
        out = set()
        for other in self.discover():
            if other.id != ep.id and other.territory not in ("ALL", ep.territory) and other.driver != "calendar":
                if any(w in weeks for w in other.active):
                    out.add(other.territory)
        return sorted(out)

    def episode_weeks(self, ep: Episode) -> list[str]:
        return [w for w in self.usable if w in ep.active]

    def compare(self, episode_id: str, exclude_controls: list[str] | None = None) -> Comparison:
        ep = self.episodes.get(episode_id)
        if ep is None:
            raise Refused(f"Unknown episode id {episode_id!r}. Use an id from the candidate list.")
        weeks = self.episode_weeks(ep)
        if not weeks:
            raise Refused(f"{episode_id} is not active in any usable week of this scope.")
        if ep.driver == "calendar":
            raise Refused("The forecast already models holidays and business days, so a holiday cannot be compared "
                          "against controls. Reject it with that reason, or leave it.")
        cid = f"K{len(self.comparisons) + 1}"
        if ep.driver == "competitor":
            comp = self._compare_broad(cid, ep, weeks)
        else:
            exclude = sorted({t for t in (exclude_controls or []) + self.dropped if t in T and t != ep.territory})
            unknown = [t for t in (exclude_controls or []) if t not in T]
            if unknown:
                raise Refused(f"Unknown territory id(s): {', '.join(unknown)}. Use: {', '.join(T)}.")
            if len(T) - 1 - len(exclude) < 4:
                raise Refused("Keep at least four control territories. exclude_controls lists only the few territories "
                              "with an episode of their own in those weeks; it is usually empty. "
                              f"For {ep.id} those are: {', '.join(self.contaminated(ep, self.episode_weeks(ep))) or 'none'}.")
            comp = self._compare_local(cid, ep, weeks, exclude)
        self.comparisons[cid] = comp
        return comp

    def _compare_local(self, cid: str, ep: Episode, weeks: list[str], exclude: list[str]) -> Comparison:
        r = self.reg
        controls = [t for t in T if t != ep.territory and t not in exclude]
        if not controls:
            raise Refused("No control territory is left.")
        effect_sql = S.excess(ep.territory, weeks, controls)
        effect = r.scalar(effect_sql) or 0.0
        f_exp = r.scalar(S.fva("forecast_trx", weeks, ep.territory)) or 1
        exp_rate = 100 * (r.scalar(S.fva("variance_trx", weeks, ep.territory)) or 0) / f_exp
        rates = []
        for c in controls:
            f = r.scalar(S.fva("forecast_trx", weeks, c)) or 1
            rates.append(100 * (r.scalar(S.fva("variance_trx", weeks, c)) or 0) / f)
        ctrl_rate = 100 * (r.scalar(f"select {S.rate(weeks, controls)}") or 0)
        spread = statistics.pstdev(rates) if len(rates) > 1 else None
        start = ep.active[0]
        pre = [w for w in (shift(start, -i) for i in range(8, 0, -1)) if w >= self.first and w not in self.provisional]
        placebo_rate = None
        if pre:
            fp = r.scalar(S.fva("forecast_trx", pre, ep.territory)) or 1
            placebo_rate = 100 * (r.scalar(S.excess(ep.territory, pre, controls)) or 0) / fp
        effect_rate = 100 * effect / f_exp
        flags = []
        contaminated = [c for c in self.contaminated(ep, weeks) if c in controls]
        if contaminated:
            flags.append("contaminated_controls")
        if len(controls) < 4:
            flags.append("few_controls")
        if placebo_rate is not None and abs(placebo_rate) >= 2 and placebo_rate * effect_rate > 0:
            if abs(placebo_rate) >= PLACEBO_FULL * abs(effect_rate):
                flags.append("gap_predates_episode")
            elif abs(placebo_rate) >= PLACEBO_PARTIAL * abs(effect_rate):
                flags.append("partial_pre_period_gap")
        if spread is not None and abs(exp_rate - ctrl_rate) < 2 * spread:
            flags.append("within_control_noise")
        if effect * ep.direction < 0:
            flags.append("opposite_to_expected_direction")
        stats = {"effect_trx": round(effect, 1), "effect_pct_of_forecast": round(effect_rate, 1),
                 "exposed_miss_pct": round(exp_rate, 1), "control_miss_pct": round(ctrl_rate, 1),
                 "control_spread_points": round(spread, 1) if spread is not None else None,
                 "pre_period_excess_pct": round(placebo_rate, 1) if placebo_rate is not None else None,
                 "n_controls": len(controls), "weeks_compared": len(weeks), "contaminated_controls_kept": contaminated}
        return Comparison(cid, ep.id, "exposed_vs_control", weeks, controls, effect, effect_sql, stats, flags)

    def share_window(self, weeks: list[str]) -> list[str]:
        """At least four weeks around the scope (one after, then one before, in turn), so one noisy week does not
        set the share."""
        out, before = sorted(weeks), False
        while len(out) < 4:
            cand = shift(out[0], -1) if before else shift(out[-1], 1)
            if self.first <= cand <= self.latest:
                out = sorted(out + [cand])
            elif not (self.first <= shift(out[0], -1) or shift(out[-1], 1) <= self.latest):
                break
            before = not before
        return out

    def _compare_broad(self, cid: str, ep: Episode, weeks: list[str]) -> Comparison:
        launched = ep.active[0]
        pre = [shift(launched, -i) for i in range(4, 0, -1)]
        sw = self.share_window(weeks)
        effect_sql = f"select ({S.fva('forecast_trx', weeks, self.cut)}) * {S.share_loss(sw, pre, T)}"
        effect = self.reg.scalar(effect_sql) or 0.0
        before, after = self.reg.scalar(S.bxa_share(pre, T)), self.reg.scalar(S.bxa_share(sw, T))
        stats = {"effect_trx": round(effect, 1), "bxa_share_before_launch_pct": round(before or 0, 1),
                 "bxa_share_in_scope_pct": round(after or 0, 1), "relative_share_change_pct":
                 round(100 * ((after or 0) / (before or 1) - 1), 1), "share_weeks": len(sw)}
        flags = ["no_control_territory"]
        if effect >= 0:
            flags.append("opposite_to_expected_direction")
        return Comparison(cid, ep.id, "share_loss", weeks, [], effect, effect_sql, stats, flags)

    # ---- stage 4: verdicts ---------------------------------------------------------------------------
    def accept(self, episode_id: str, comparison_id: str, reason: str, by: str) -> None:
        ep, comp = self.episodes.get(episode_id), self.comparisons.get(comparison_id)
        if ep is None:
            raise Refused(f"Unknown episode id {episode_id!r}. Candidates: {', '.join(self.episodes)}.")
        if comp is None:
            mine = [k.id for k in self.comparisons.values() if k.episode == episode_id]
            raise Refused(f"Unknown comparison id {comparison_id!r}. " + (f"Comparisons run for {episode_id}: {', '.join(mine)}."
                          if mine else f"No comparison has been run for {episode_id}; call compare first."))
        if comp.episode != ep.id:
            raise Refused(f"{comparison_id} compares {comp.episode}, not {episode_id}.")
        if self.cut != "NATIONAL" and ep.territory not in (self.cut, "ALL"):
            raise Refused(f"{episode_id} is outside {name(self.cut)}.")
        reason = no_digits(reason)
        ep.status, ep.comparison, ep.reason = "accepted", comp.id, reason
        self.decide(by, "accept", f"{ep.id} {ep.label} using {comp.id}", reason)

    def reject(self, episode_id: str, reason: str, by: str) -> None:
        ep = self.episodes.get(episode_id)
        if ep is None:
            raise Refused(f"Unknown episode id {episode_id!r}.")
        reason = no_digits(reason)
        ep.status, ep.comparison, ep.reason = "rejected", None, reason
        self.decide(by, "reject", f"{ep.id} {ep.label}", reason)

    def abstain(self, reason: str, by: str) -> None:
        self.abstained = no_digits(reason)
        self.decide(by, "abstain", self.scope.period, self.abstained)

    def accepted(self) -> list[tuple[Episode, Comparison]]:
        return [(e, self.comparisons[e.comparison]) for e in self.episodes.values() if e.status == "accepted" and e.comparison]

    # ---- stage 5: robustness checks, run by code on every accepted local driver -------------------------
    def robustness(self, ep: Episode, comp: Comparison) -> dict:
        """Leave-one-out over the controls, and whether the gap narrowed once the episode ended."""
        if comp.method != "exposed_vs_control":
            return {}
        if "robustness" in comp.stats:
            return comp.stats["robustness"]
        r, out = self.reg, {}
        if len(comp.controls) > 2 and comp.effect:
            moves = []
            for c in comp.controls:
                rest = [x for x in comp.controls if x != c]
                moves.append(abs((r.scalar(S.excess(ep.territory, comp.weeks, rest)) or 0) - comp.effect) / abs(comp.effect))
            out["leave_one_out_max_change_pct"] = round(100 * max(moves), 1)
        after = shift(ep.active[-1], 1)
        bad = {t for (t,) in r.rows(f"select territory_id from {S.FVA} where product_id = 'BXA' and actual_is_provisional = 1 "
                                    f"and week_start = DATE '{after}'")} if after <= self.latest else set()
        controls = [c for c in comp.controls if c not in bad]
        if after <= self.latest and ep.territory not in bad and len(controls) >= 4:
            gap_after = 100 * ((r.scalar(f"select {S.rate([after], ep.territory)}") or 0) - (r.scalar(f"select {S.rate([after], controls)}") or 0))
            out["gap_after_points"] = round(gap_after, 1)
            out["gap_during_points"] = round(comp.stats["exposed_miss_pct"] - comp.stats["control_miss_pct"], 1)
        comp.stats["robustness"] = out
        return out

    # ---- stage 5: challenge (code-confirmed; it can only lower confidence) ----------------------------
    def confidence(self, ep: Episode, comp: Comparison) -> tuple[str, list[str]]:
        cap, reasons = "high", []

        def limit(level: str, why: str) -> None:
            nonlocal cap
            reasons.append(why)
            if LEVELS.index(level) < LEVELS.index(cap):
                cap = level

        if ep.driver == "competitor":
            limit("medium", "turning share loss into TRx assumes the basket would otherwise have matched the forecast")
            limit("medium", "no territory escaped the launch, so there is no control group")
            if any(e.status == "accepted" and e.driver != "competitor" for e in self.episodes.values()):
                reasons.append("the national share also reflects local episodes, so this estimate may overlap them")
        if ep.driver == "promotion":
            limit("medium", "aggregated promotion is an association with the miss, not proof of cause")
        flags = set(comp.flags)
        if "few_controls" in flags:
            limit("medium", "fewer than four control territories")
        if "contaminated_controls" in flags:
            limit("medium", "a control territory has an episode of its own in these weeks")
        if "within_control_noise" in flags:
            limit("low", "the exposed territory's miss rate is within twice the spread across control territories")
        if "partial_pre_period_gap" in flags:
            limit("medium", "the territory already ran somewhat behind its controls in the weeks before the episode")
        if "gap_predates_episode" in flags:
            limit("low", "the territory already ran behind its controls before the episode began")
        if "opposite_to_expected_direction" in flags:
            limit("low", "the estimate points the opposite way from what this kind of episode would do")
        rob = self.robustness(ep, comp)
        if rob.get("leave_one_out_max_change_pct", 0) > 100 * LOO_SHARE:
            limit("medium", "the estimate moves by more than a quarter when a single control territory is dropped")
        during, after = rob.get("gap_during_points"), rob.get("gap_after_points")
        if during and after is not None and after * during > 0 and abs(after) >= RECOVERY_SHARE * abs(during) \
                and ep.driver != "access":
            limit("medium", "the gap did not narrow in the week after the episode ended")
        overlap = [o for o, oc in self.accepted() if o.id != ep.id and o.territory == ep.territory
                   and set(oc.weeks) & set(comp.weeks)]
        if overlap:
            limit("medium", "another accepted episode overlaps it in the same territory and weeks, so the split between them is not identified")
        passed = []
        if "leave_one_out_max_change_pct" in rob and rob["leave_one_out_max_change_pct"] <= 100 * LOO_SHARE:
            passed.append("the estimate holds when any one control territory is dropped")
        if during and after is not None and not (after * during > 0 and abs(after) >= RECOVERY_SHARE * abs(during)):
            passed.append("the gap narrowed once the episode ended")
        if not reasons:
            reasons.append("clean controls, no pre-period gap, and the effect is well outside control noise")
        reasons += passed
        return cap, reasons

    def unexplained(self, screen: list[dict]) -> list[dict]:
        """Territories that stand out beyond their peers with no accepted episode covering them."""
        covered = {e.territory for e, _ in self.accepted()}
        return [r for r in screen if r["standout"] and r["beyond_peers"] < 0 and r["territory"] not in covered
                and (self.cut == "NATIONAL" or r["territory"] == self.cut)]
