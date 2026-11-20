"""Stage 5 and 6: code writes the answer. Every figure is a claim token filled from one governed query; the
only free text from a model is a decision reason, which the engine already refused if it held a digit."""
from __future__ import annotations

from datetime import date, timedelta

from pharmagentics.tools.queries import name, shift
from pharmagentics.tools.registry import FORMATS, digits_outside_tokens

from . import sql as S
from .engine import OWNER, Case, Comparison, Episode

T = S.TERRITORIES
ORDER = {
    "reliability": ["miss", "data", "where"],
    "screen": ["screen"],
    "where": ["miss", "data", "where"],
    "drivers": ["miss", "data", "candidates", "attribution", "confidence", "checks"],
    "attribution": ["miss", "data", "attribution", "confidence", "candidates", "unknowns", "checks"],
    "unknowns": ["miss", "data", "confidence", "unknowns", "attribution", "checks"],
    "next_checks": ["miss", "data", "checks", "attribution"],
    "assumptions": ["miss", "data", "assumptions", "attribution", "candidates"],
    "audit": ["miss", "data", "attribution", "audit"],
    "communicate": ["summary", "miss", "attribution", "unknowns"],
}
TITLES = {"miss": "The miss", "data": "Data checks", "where": "Where", "screen": "Largest gaps",
          "candidates": "What was investigated", "attribution": "Attribution", "confidence": "Confidence by driver",
          "unknowns": "What remains unknown", "checks": "What to check next", "assumptions": "Forecast assumptions",
          "audit": "Audit", "summary": "Summary for leadership"}
FRACTIONS = [(1.0, "all"), (0.75, "three-quarters"), (2 / 3, "two-thirds"), (0.5, "half"), (1 / 3, "one-third"),
             (0.25, "one-quarter"), (0.2, "one-fifth"), (1 / 6, "one-sixth"), (1 / 7, "one-seventh"), (0.125, "one-eighth"),
             (0.1, "one-tenth")]


def fraction_words(x: float) -> str:
    x = abs(x)
    if x < 0.07:
        return "a small part"
    return "about " + min(FRACTIONS, key=lambda f: abs(f[0] - x))[1]


def _names(terrs: list[str]) -> str:
    names = [name(t) if t.isupper() else t for t in terrs]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _span(weeks: list[str]) -> str:
    return f"the week of {weeks[0]}" if len(weeks) == 1 else f"the weeks of {weeks[0]} to {weeks[-1]}"


def _possessive(n: str) -> str:
    return n + ("'" if n.endswith("s") else "'s")


def _pretty(label: str) -> str:
    return label.replace("_", " ").title().replace(" Week Week", " Week") if label.isupper() else label


class Writer:
    def __init__(self, case: Case):
        self.case, self.reg = case, case.reg
        self.W = case.usable or case.weeks
        self.cut = case.cut
        self.v_sql = S.fva("variance_trx", self.W, self.cut)
        self.V = self.reg.scalar(self.v_sql) or 0.0

    def c(self, tool: str, sql: str, fmt: str = "int", **params) -> str:
        return self.reg.claim(tool, sql, fmt, **params)

    # ---- components: usual bias, accepted drivers, residual (V = sum of components + residual) -------
    def components(self) -> list[dict]:
        case, out = self.case, []
        if case.abstained or not case.usable:
            return out
        if case.launch:
            out.append({"key": "bias", "label": "Usual forecast bias", "driver": "bias", "territory": self.cut,
                        "sql": S.bias(self.W, self.cut, case.launch), "episode": None, "comparison": None})
        for ep, comp in sorted(case.accepted(), key=lambda ec: ec[1].effect):
            out.append({"key": ep.id, "label": ep.label, "driver": ep.driver, "territory": ep.territory,
                        "sql": comp.effect_sql, "episode": ep, "comparison": comp})
        for part in out:
            part["value"] = self.reg.scalar(part["sql"]) or 0.0
        return out

    # ---- sections -----------------------------------------------------------------------------------
    def header(self) -> str:
        case = self.case
        issue = self.reg.fact("get_forecast_version", f"select min(forecast_issue_week)::varchar from {S.FVA} where product_id = 'BXA' "
                              f"and territory_id = '{self.cut}' and week_start = DATE '{case.weeks[0]}'")
        lines = [f"Forecast explanation for {name(self.cut)}, {_span(case.weeks)}. Data version {self.reg.data_version}. "
                 f"The locked forecast for the first week was issued {issue}, four weeks ahead."]
        lines += case.scope.notes
        return "\n".join(lines)

    def miss(self) -> str:
        case, W = self.case, self.case.weeks
        if case.cut_provisional():
            f = self.c("get_forecast", S.fva("forecast_trx", W, self.cut), cut=self.cut)
            a = self.c("get_forecast", S.fva("actual_trx", W, self.cut), cut=self.cut)
            v = self.c("get_forecast", S.fva("variance_trx", W, self.cut), cut=self.cut)
            p = self.c("get_forecast", S.pct_of_forecast(W, self.cut), "pct1", cut=self.cut)
            return (f"The forecast was {f} TRx and the reported actual {a}: a gap of {v} TRx, {p} of forecast. "
                    "That actual is provisional, so the gap is not a settled miss and is not attributed.")
        U = self.W
        f = self.c("get_forecast", S.fva("forecast_trx", U, self.cut), cut=self.cut)
        a = self.c("get_forecast", S.fva("actual_trx", U, self.cut), cut=self.cut)
        v = self.c("get_forecast", self.v_sql, cut=self.cut)
        p = self.c("get_forecast", S.pct_of_forecast(U, self.cut), "pct1", cut=self.cut)
        word = "below" if self.V < 0 else "above"
        scope = "" if len(U) == len(W) else " over the weeks with final actuals"
        text = (f"Forecast {f} TRx, actual {a} TRx{scope}. The miss (actual minus forecast) is {v} TRx, "
                f"{p} {word} forecast, as a percent of forecast.")
        if len(U) != len(W):
            va = self.c("get_forecast", S.fva("variance_trx", W, self.cut), cut=self.cut, weeks="all")
            pa = self.c("get_forecast", S.pct_of_forecast(W, self.cut), "pct1", cut=self.cut, weeks="all")
            text += (f" Including the weeks with a provisional actual, the reported gap is {va} TRx ({pa} of forecast); "
                     "that figure may still change.")
        return text

    def data(self) -> str:
        case = self.case
        lines = []
        if case.cut_provisional():
            for t in sorted({c for _, c in case.provisional_cuts if self.cut == "NATIONAL" or c in (self.cut, "NATIONAL")}):
                if t == "NATIONAL":
                    continue
                for w in [w for w, c in case.provisional_cuts if c == t]:
                    miss = self.c("validate_feed", f"select missing_key_count from reporting.v_feed_health where week_start = DATE '{w}' and territory_id = '{t}'", territory=t)
                    cov = self.c("validate_feed", f"select panel_coverage_ratio from reporting.v_feed_health where week_start = DATE '{w}' and territory_id = '{t}'", "dec3", territory=t)
                    reasons = next((", ".join(f["reasons"]) for f in case.flags if f["week"] == w and f["territory"] == t), "a provisional feed")
                    lines.append(f"{name(t)}, week of {w}: {reasons}. Missing keys {miss}; panel coverage {cov}.")
            if self.cut == "NATIONAL":
                lines.append("The national actual that week is provisional too, because it sums the territories.")
            lines.append("Nothing is attributed until the feed is reloaded. Next: ask the data vendor for the reload, "
                         "then ask this question again.")
            return "\n".join(lines)
        if case.provisional:
            lines.append(f"Set aside: the actual is provisional in the week(s) of {', '.join(case.provisional)}, "
                         "so those weeks are kept out of the miss and every comparison.")
        others = [f for f in case.flags if f["week"] not in case.provisional]
        for f in others[:4]:
            lines.append(f"Flagged but final: {name(f['territory'])}, week of {f['week']} ({', '.join(f['reasons'])}).")
        if not lines:
            lines.append("Every cut in these weeks passes the feed checks; the actuals are final.")
        return "\n".join(lines)

    def where(self, top: int = 3) -> str:
        if self.cut != "NATIONAL":
            peers = [t for t in T if t != self.cut]
            ex = self.c("screen_territories", S.excess(self.cut, self.W, peers), territory=self.cut)
            rp = self.c("screen_territories", S.pct_rate(self.W, peers), "pct1", scope="other territories")
            return (f"The other territories missed by {rp} of forecast over the same weeks. Against their rate, "
                    f"{name(self.cut)} is {ex} TRx beyond what they predict.")
        rows = self.case.screen(self.W)
        lines = []
        below = sum(1 for r in rows if r["miss"] < 0)
        for r in rows[:top]:
            t = r["territory"]
            v = self.c("screen_territories", S.fva("variance_trx", self.W, t), territory=t)
            p = self.c("screen_territories", S.pct_of_forecast(self.W, t), "pct1", territory=t)
            sv = self.c("screen_territories", S.share_of(S.fva("variance_trx", self.W, t), self.v_sql), "pct1", territory=t)
            sf = self.c("screen_territories", S.share_of(S.fva("forecast_trx", self.W, t), S.fva("forecast_trx", self.W)), "pct1", territory=t)
            lines.append(f"- {name(t)}: {v} TRx ({p} of its forecast), {sv} of the national miss from {sf} of the forecast.")
        tie = self.c("screen_territories", S.fva("variance_trx", self.W, T), scope="sum of territories")
        shape = "every territory is" if below == len(rows) else ("most territories are" if below > len(rows) / 2 else "a few territories are")
        lines.append(f"In these weeks {shape} below forecast. The eight territories sum to {tie} TRx, which ties to the national figure.")
        return "\n".join(lines)

    def screen(self, n: int = 5) -> str:
        rows = self.case.screen(self.W)[:n]
        lines = [f"Largest misses by territory over {_span(self.W)}, with each territory's miss beyond what the "
                 "other territories' rate predicts:"]
        for r in rows:
            t = r["territory"]
            peers = [p for p in T if p != t]
            v = self.c("screen_territories", S.fva("variance_trx", self.W, t), territory=t)
            p = self.c("screen_territories", S.pct_of_forecast(self.W, t), "pct1", territory=t)
            ex = self.c("screen_territories", S.excess(t, self.W, peers), territory=t)
            mark = " Stands out." if r["standout"] and r["beyond_peers"] < 0 else ""
            lines.append(f"- {name(t)}: miss {v} TRx ({p} of forecast); beyond peers {ex}.{mark}")
        stand = [r["territory"] for r in self.case.screen(self.W) if r["standout"] and r["beyond_peers"] < 0]
        if stand:
            lines.append(f"Only {_names(stand)} missed well beyond the rate the others share; the rest move with the "
                         "broad miss. Ask about a standout territory to investigate it.")
        else:
            lines.append("No territory missed well beyond the rate the others share: the miss is broad.")
        if self.case.provisional:
            lines.append(f"Weeks with a provisional actual are left out: {', '.join(self.case.provisional)}.")
        return "\n".join(lines)

    def _signal(self, ep: Episode) -> str:
        weeks = [w for w in ep.active if w in self.case.weeks] or ep.active
        t = ep.territory
        if ep.driver == "promotion":
            a = self.c("lookup_promo", S.context_mean("promo_activity", "rep_calls_aggregated", weeks, t), territory=t)
            b = self.c("lookup_promo", f"select median(rep_calls_aggregated) from raw.promo_activity where product_id = 'BXA' and territory_id = '{t}'", territory=t)
            med = f"select median(rep_calls_aggregated) from raw.promo_activity where product_id = 'BXA' and territory_id = '{t}'"
            mean = S.context_mean("promo_activity", "rep_calls_aggregated", weeks, t)
            lower = self.c("lookup_promo", f"select 100.0 * (1 - ({mean}) / nullif(({med}), 0))", "pct1", territory=t)
            return f"aggregated rep calls averaged {a} a week against a usual {b}, {lower} lower"
        if ep.driver == "supply":
            lo = self.c("lookup_inventory", f"select min(inventory_fill_rate) from raw.inventory_weekly where product_id = 'BXA' and territory_id = '{t}' and week_start in {S.dates(weeks)}", "dec2", territory=t)
            hi = self.c("lookup_inventory", f"select max(inventory_fill_rate) from raw.inventory_weekly where product_id = 'BXA' and territory_id = '{t}' and week_start in {S.dates(weeks)}", "dec2", territory=t)
            f = f"{lo} to {hi}, averaging " + self.c("lookup_inventory", S.context_mean("inventory_weekly", "inventory_fill_rate", weeks, t), "dec2", territory=t)
            b = self.c("lookup_inventory", S.context_mean("inventory_weekly", "distribution_backorder_rate", weeks, t, 100), "pct1", territory=t)
            return f"inventory fill ran {f}, with {b} of orders backordered"
        if ep.driver == "access":
            plan = ep.signal["plan"]
            lives = self.c("lookup_access_events", f"select 100.0 * (select max(covered_lives_weight) from raw.dim_plan where plan_id = '{plan}') / "
                           f"(select sum(covered_lives_weight) from raw.dim_plan where territory_id = '{t}')", "pct1", plan=plan)
            return f"effective {ep.signal['effective_month']}, on a plan with {lives} of the territory's covered lives"
        if ep.driver == "competitor":
            pre = [shift(ep.active[0], -i) for i in range(4, 0, -1)]
            sw = self.case.share_window(self.case.episode_weeks(ep) or self.W)
            s0 = self.c("share_loss", S.bxa_share(pre, T), "pct1", weeks="before launch")
            s1 = self.c("share_loss", S.bxa_share(sw, T), "pct1", weeks="in scope")
            c1 = self.c("share_loss", S.product_share(sw, ep.signal["product"], T), "pct1", weeks="in scope")
            return (f"launched {ep.active[0]}; it holds {c1} of the basket in these weeks, and the brand's share went "
                    f"from {s0} before launch to {s1}")
        if ep.driver == "calendar":
            return f"week of {ep.active[0]}"
        return ""

    def candidates(self) -> str:
        eps = list(self.case.episodes.values())
        if not eps:
            return "No access change, promotion lapse, supply shortfall, competitor launch or holiday is visible in these weeks."
        lines = []
        for ep in eps:
            verdict = {"accepted": "Supported", "rejected": "Ruled out", "candidate": "Not tested"}[ep.status]
            why = f" {ep.reason[0].upper()}{ep.reason[1:]}." if ep.reason else ""
            lines.append(f"- {_pretty(ep.label)} ({self._signal(ep)}): {verdict}.{why}")
        lines += self._absent({"access", "promotion", "supply", "competitor"} - {e.driver for e in eps})
        return "\n".join(lines)

    def _absent(self, absent: set[str]) -> list[str]:
        """Evidence for the drivers with no episode, so the answer says what contradicts them, not only what supports."""
        if not absent:
            return []
        W, out = self.W, []
        if self.cut != "NATIONAL":
            from pharmagentics.tools import checks as shared
            ref = [shift(W[0], -i) for i in range(13, 0, -1)]
            fn = {"access": shared.check_access, "promotion": shared.check_promotion, "supply": shared.check_supply,
                  "competitor": shared.check_competitor}
            for d in ("access", "promotion", "supply", "competitor"):
                if d in absent:
                    out.append("- " + fn[d](self.reg, self.cut, W, ref).text)
            return out
        if "supply" in absent:
            lo = self.c("lookup_inventory", f"select min(inventory_fill_rate) from raw.inventory_weekly where product_id = 'BXA' and week_start in {S.dates(W)}", "dec3")
            out.append(f"- Supply: no territory's BXA inventory fill fell below {lo} in these weeks.")
        if "access" in absent:
            out.append("- Access: no BXA tier, prior authorization, step therapy or coverage change in these months.")
        if "promotion" in absent:
            out.append("- Promotion: no territory's aggregated rep calls lapsed in these weeks.")
        if "competitor" in absent:
            out.append("- Competitor: no launch in the basket by these weeks.")
        return out

    def attribution(self, parts: list[dict]) -> str:
        if self.case.abstained:
            return f"No attribution: {self.case.abstained}."
        lines = ["Signed TRx, actual minus forecast. The parts plus the residual equal the miss."]
        for p in parts:
            v = self.c("reconcile_attribution", p["sql"], driver=p["label"])
            lines.append(f"- {_pretty(p['label'])}: {v}. {self._method(p)}")
        res = self.c("reconcile_attribution", S.minus(self.v_sql, [p["sql"] for p in parts]), driver="residual")
        lines.append(f"- Unexplained residual: {res}. It is shown, not spread across the drivers.")
        local = [p for p in parts if p["driver"] not in ("bias", "competitor")]
        if self.cut != "NATIONAL" and len(local) == 1:
            comp: Comparison = local[0]["comparison"]
            rate = self.c("compare_exposed_control", S.at_rate(self.cut, comp.weeks, comp.controls), territory=self.cut)
            lines.append(f"At the control territories' rate, {name(self.cut)} would have missed by {rate} TRx in those weeks.")
        return "\n".join(lines)

    def _method(self, p: dict) -> str:
        if p["driver"] == "bias":
            r = self.c("get_forecast", f"select 100.0 * {S.bias_rate(self.case.launch)}", "pct1", window="before launch")
            return (f"Method: before the competitor launch the national forecast ran {r} high on average; "
                    "that rate applied to this forecast.")
        comp: Comparison = p["comparison"]
        if comp.method == "share_loss":
            ep = p["episode"]
            pre = [shift(ep.active[0], -i) for i in range(4, 0, -1)]
            sw = self.case.share_window(comp.weeks)
            loss = self.c("share_loss", f"select 100.0 * {S.share_loss(sw, pre, T)}", "pct1")
            return (f"Method: the brand's basket share fell by {loss} relative to before the launch; that loss applied "
                    "to the forecast. It assumes the basket would otherwise have matched the forecast.")
        rate = self.c("compare_exposed_control", S.pct_rate(comp.weeks, comp.controls), "pct1", scope="controls")
        own = self.c("compare_exposed_control", S.pct_of_forecast(comp.weeks, p["territory"]), "pct1", territory=p["territory"])
        text = (f"Method: {name(p['territory'])} missed by {own} of forecast while the control territories "
                f"({_names(comp.controls)}) missed by {rate}, over {_span(comp.weeks)}. The estimate is the gap beyond "
                "the controls' rate: an association with the episode, not proof of cause.")
        return text + self._recovery(p["episode"], comp)

    def _recovery(self, ep: Episode, comp: Comparison) -> str:
        """Did the gap close when the episode ended? A check that supports or contradicts the episode."""
        after = shift(ep.active[-1], 1)
        if after > self.case.latest:
            return ""
        bad = {t for (t,) in self.reg.rows(f"select territory_id from {S.FVA} where product_id = 'BXA' "
                                          f"and actual_is_provisional = 1 and week_start = DATE '{after}'")}
        controls = [c for c in comp.controls if c not in bad]
        if ep.territory in bad or len(controls) < 4:
            return ""
        nxt = self.c("compare_exposed_control", S.pct_of_forecast([after], ep.territory), "pct1", territory=ep.territory, week=after)
        ctl = self.c("compare_exposed_control", S.pct_rate([after], controls), "pct1", scope="controls", week=after)
        return f" In the week after it ended ({after}), {name(ep.territory)} missed by {nxt} against {ctl} for the controls."

    def confidence(self, parts: list[dict]) -> str:
        lines = []
        for p in parts:
            if p["episode"] is None:
                continue
            level, reasons = self.case.confidence(p["episode"], p["comparison"])
            text = "; ".join(reasons)
            lines.append(f"- {_pretty(p['label'])}: {level}. {text[0].upper()}{text[1:]}.")
        if not lines:
            return "No driver is quantified, so there is no driver confidence to state. The whole miss is unexplained."
        lines.append("- The residual is an open unknown, not noise by assumption.")
        return "\n".join(lines)

    def unknowns(self, parts: list[dict]) -> str:
        lines = []
        if not self.case.abstained:
            res = self.c("reconcile_attribution", S.minus(self.v_sql, [p["sql"] for p in parts]), driver="residual")
            lines.append(f"The residual, {res} TRx, has no identified driver.")
        for r in self.case.unexplained(self.case.screen(self.W)):
            t = r["territory"]
            ex = self.c("screen_territories", S.excess(t, self.W, [p for p in T if p != t]), territory=t)
            lines.append(f"{name(t)} ran {ex} TRx beyond the other territories' rate with no visible driver in the context tables.")
        untested = [e for e in self.case.episodes.values() if e.status == "candidate"]
        if untested:
            lines.append("Not tested: " + "; ".join(_pretty(e.label) for e in untested) + ".")
        return "\n".join(lines) or "Nothing else stands out."

    def checks(self, parts: list[dict]) -> list[dict]:
        out = []
        for p in parts:
            ep = p["episode"]
            if ep is None:
                continue
            if ep.driver == "competitor":
                out.append({"question": "Review the competitor assumption in the forecast.", "owner": OWNER["competitor"],
                            "why": "The launch is outside the locked forecast by design, and the gap persists."})
            else:
                out.append({"question": f"Confirm the {_pretty(ep.label)} finding and whether it has ended.",
                            "owner": OWNER[ep.driver], "why": "It is the supported local driver in these weeks."})
        for r in self.case.unexplained(self.case.screen(self.W)):
            out.append({"question": f"Split the {name(r['territory'])} gap by plan and specialty.", "owner": OWNER["residual"],
                        "why": "It stands out from the other territories with no visible driver."})
        if self.case.abstained:
            out.append({"question": "Reload the provisional feed, then ask again.", "owner": OWNER["data"],
                        "why": "The actual is provisional."})
        else:
            out.append({"question": "Split the unexplained residual by plan and specialty.", "owner": OWNER["residual"],
                        "why": "Part of the miss has no identified driver."})
        return out

    def checks_text(self, checks: list[dict]) -> str:
        return "\n".join(f"- {c['owner']}: {c['question']} {c['why']}" for c in checks)

    def assumptions(self) -> str:
        launch = self.case.launch
        if not launch:
            return "No competitor launch is visible, so the forecast's competitive assumption has nothing to test."
        end = self.case.weeks[-1] if self.case.weeks[-1] >= launch else self.case.latest
        pre = self.c("get_forecast", S.monthly_national_pct(self.case.first, shift(launch, -1)), "pct1", window="before launch")
        lines = [f"Before the launch on {launch}, the national forecast missed by {pre} of forecast on average."]
        start, stop_at, parts = date.fromisoformat(launch), date.fromisoformat(end), []
        while start <= stop_at:
            month = start.month - 1 + 2
            nxt = date(start.year + month // 12, month % 12 + 1, 1)
            last = min(nxt - timedelta(days=1), stop_at).isoformat()
            p = self.c("get_forecast", S.monthly_national_pct(start.isoformat(), last), "pct1", window=f"{start.isoformat()} to {last}")
            parts.append(f"{start.isoformat()} to {last}: {p}")
            start = nxt
        lines.append("Since the launch, in two-month steps: " + "; ".join(parts) + ".")
        lines.append("A persistent, broad gap that starts at the launch points to the competitor assumption, not to "
                     "one-off local shocks. This is a review trigger for Forecasting; this agent changes no forecast.")
        return "\n".join(lines)

    def audit(self) -> str:
        tie = self.c("validate_and_quantify", f"select count(*) from (select week_start from {S.FVA} where product_id = 'BXA' "
                     "group by 1 having sum(forecast_trx) filter (where territory_id <> 'NATIONAL') = sum(forecast_trx) filter (where territory_id = 'NATIONAL') "
                     "and sum(actual_trx) filter (where territory_id <> 'NATIONAL') = sum(actual_trx) filter (where territory_id = 'NATIONAL'))", scope="release")
        weeks = self.c("validate_and_quantify", "select count(*) from raw.calendar", scope="release")
        return (f"In {tie} of the {weeks} weeks of the release, the territory forecasts and actuals sum exactly to the "
                f"national figures. Every figure in this answer is a stored query on data version {self.reg.data_version}. Each was run "
                "again and returned the same value. The parts and the residual sum to the miss by construction, and "
                "no provisional week enters a comparison.")

    def summary(self, parts: list[dict]) -> str:
        if self.case.abstained:
            return "The reported gap rests on a provisional actual, so no explanation is offered until the feed is reloaded."
        p = self.c("get_forecast", S.pct_of_forecast(self.W, self.cut), "pct1", cut=self.cut)
        word = "below" if self.V < 0 else "above"
        where = "nationally" if self.cut == "NATIONAL" else f"in {name(self.cut)}"
        lines = [f"Cardiovela was {p} {word} forecast {where} over {_span(self.W)}."]
        named = [q for q in parts if q["episode"] is not None and q["value"] * self.V > 0]
        for q in sorted(named, key=lambda q: -abs(q["value"]))[:2]:
            lines.append(f"{fraction_words(q['value'] / self.V).capitalize()} of the gap matches the {_pretty(q['label'])}.")
        residual = self.V - sum(q["value"] for q in parts)
        lines.append(f"{fraction_words(residual / self.V).capitalize()} is not explained yet." if self.V else "")
        return " ".join(x for x in lines if x)


def _whole(x: float) -> float:
    """Whole TRx, rounded half up like the claim tokens, so the table and the text show the same figure."""
    return float(FORMATS["int"](x).replace(",", ""))


def _verify(case: Case, w: Writer, parts: list[dict], template: str) -> dict:
    checks = []

    def add(cid: str, ok: bool, detail: str, warn: bool = False) -> None:
        checks.append({"id": cid, "status": "pass" if ok else ("warn" if warn else "fail"), "detail": detail})

    total = sum(p["value"] for p in parts)
    residual = w.V - total
    add("arithmetic", True, "the parts plus the residual equal the miss (computed in one query)")
    add("no_provisional", not any(set(c.weeks) & set(case.provisional) for c in case.comparisons.values()),
        "no provisional week enters a comparison")
    add("digits_from_code", not digits_outside_tokens(template), "every digit in the answer comes from a claim token")
    add("reasons_have_no_digits", True, "decision reasons were checked when they were given")
    if parts and w.V:
        add("residual_size", abs(residual) <= 0.5 * abs(w.V), "the residual is under half of the miss", warn=True)
    against = [p["label"] for p in parts if p["episode"] is not None and p["value"] * w.V < 0]
    add("direction", not against, "every driver points the same way as the miss" if not against
        else f"against the miss: {', '.join(_pretty(a) for a in against)}", warn=True)
    status = {c["status"] for c in checks}
    verdict = "FAIL" if "fail" in status else "WARN" if "warn" in status else "PASS"
    return {"verdict": verdict, "checks": checks}


def compose(case: Case, mode: str, trajectory: dict | None = None) -> dict:
    """The answer envelope (answer, claims, evidence) plus the structured report the UI and API read."""
    w = Writer(case)
    intent = case.scope.intent
    order = ORDER[intent]
    if case.cut_provisional():
        order = ["miss", "data"]
    parts = w.components() if not (case.cut_provisional() or intent == "screen") else []
    checks = w.checks(parts) if intent != "screen" else []
    sections, made = [], {}
    for key in order:
        if key == "screen":
            import re
            m = re.search(r"\b(?:top|largest|biggest)\s+(\d+)", case.scope.question, re.I)
            text = w.screen(int(m.group(1)) if m else 5)
        elif key == "checks":
            text = w.checks_text(checks)
        elif key in ("attribution", "confidence", "unknowns", "summary"):
            text = getattr(w, key)(parts)
        else:
            text = w.where(top=8) if key == "where" and intent == "where" else getattr(w, key)()
        made[key] = text
        sections.append({"id": key, "title": TITLES[key], "text": text})
    closing = "This report changes no forecast."
    template = "\n\n".join([w.header()] + [f"{s['title']}\n{s['text']}" for s in sections] + [closing])
    bad = digits_outside_tokens(template)
    if bad:
        raise AssertionError(f"digit outside a claim token: {bad[:3]}")
    verification = _verify(case, w, parts, template)
    reg = w.reg
    for s in sections:
        s["text"] = reg.render(s["text"])
    summary = reg.render(made["summary"]) if "summary" in made else reg.render(w.summary(parts)) if intent != "screen" else None
    var = case.variance() if case.weeks else {}
    drivers = []
    for p in parts:
        if p["episode"] is None:
            continue
        level, reasons = case.confidence(p["episode"], p["comparison"])
        comp: Comparison = p["comparison"]
        drivers.append({"driver": p["driver"], "label": _pretty(p["label"]), "territory": p["territory"],
                        "impact_trx": _whole(p["value"]), "confidence": level, "confidence_reasons": reasons,
                        "method": comp.method, "controls": comp.controls, "weeks": [comp.weeks[0], comp.weeks[-1]],
                        "evidence_ids": [e["id"] for e in reg.evidence if e["query"] == comp.effect_sql.strip()]})
    residual = None if case.abstained or not case.usable else _whole(w.V - sum(p["value"] for p in parts))
    bias = next((_whole(p["value"]) for p in parts if p["driver"] == "bias"), None)
    if intent == "screen":
        stand = [name(r["territory"]) for r in case.screen() if r["standout"] and r["beyond_peers"] < 0]
        headline = (f"Largest territory misses over {_span(w.W)}: " +
                    (f"{_names(stand)} stand{'s' if len(stand) == 1 else ''} out beyond the broad miss." if stand
                     else "the miss is broad, with no territory well beyond the others."))
    else:
        headline = (summary.split(". ")[0].rstrip(".") + "." if summary else sections[0]["text"].split("\n")[0][:160])
    report = {
        "headline": headline, "question": case.scope.question, "intent": intent, "scope": case.scope.card(),
        "territory_id": case.cut, "week_start": case.weeks[0] if case.weeks else None,
        "week_ending": shift(case.weeks[-1], 1) if case.weeks else None, "window_weeks": len(case.weeks),
        "forecast_trx": var.get("forecast"), "actual_trx": var.get("actual"), "variance_trx": var.get("variance"),
        "variance_pct": (var.get("pct") or 0) / 100 if var else None, "usable_weeks": len(case.usable),
        "set_aside_weeks": case.provisional, "bias_trx": bias, "drivers": drivers, "residual_trx": residual,
        "what_to_check": checks, "caveats": [s for s in [
            "Numbers are deterministic queries on the synthetic release; a model never supplies a figure.",
            "Local estimates compare a territory with control territories over the same weeks: an association, not proof of cause.",
            "Weeks with a provisional actual are set aside." if case.provisional else None] if s],
        "abstained": bool(case.abstained), "verification": verification, "investigator_mode": mode,
        "summary": summary, "sections": sections, "decisions": case.decisions,
        "candidates": [{**e.brief(case.weeks), "reason": e.reason, "comparison": e.comparison} for e in case.episodes.values()],
        "comparisons": [{"id": k.id, "episode": k.episode, "method": k.method, "controls": k.controls, "stats": k.stats,
                         "flags": k.flags} for k in case.comparisons.values()],
        "screen": case.screen() if case.weeks else [],
        "data_version": reg.data_version,
    }
    return {"answer": reg.render(template), "claims": reg.claims, "evidence": reg.evidence,
            "abstained": bool(case.abstained), "trajectory": trajectory, "report": report}
