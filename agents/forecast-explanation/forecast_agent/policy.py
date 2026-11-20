"""The rules policy: the same operations as the agent, chosen by fixed rules. It is the scripted arm of the
comparison and the fallback when a model fails. Reasons are fixed sentences, so they hold no digits."""
from __future__ import annotations

from .engine import Case

BAD_FLAGS = {
    "gap_predates_episode": "the territory already ran as far behind its controls before the episode began",
    "within_control_noise": "the gap is within the normal spread across control territories",
    "opposite_to_expected_direction": "the estimate points the opposite way from what this episode would do",
}


def run_rules(case: Case, by: str = "rules", only_pending: bool = False) -> None:
    if case.cut_provisional():
        if not case.abstained:
            case.abstain("every week asked about has a provisional actual, so the miss is not settled", "code")
        return
    for ep in case.discover():
        if only_pending and ep.status != "candidate":
            continue
        if ep.driver == "calendar":
            case.reject(ep.id, "the forecast already models holidays and business days", by)
            continue
        weeks = case.episode_weeks(ep)
        if not weeks:
            case.reject(ep.id, "it is not active in any usable week of this scope", by)
            continue
        if ep.driver == "competitor":
            comp = case.compare(ep.id)
            if comp.effect < 0:
                case.accept(ep.id, comp.id, "the brand lost basket share in every territory after the launch, and "
                            "the forecast leaves unplanned launches out by design", by)
            else:
                case.reject(ep.id, "the brand did not lose basket share after the launch", by)
            continue
        comp = case.compare(ep.id, case.contaminated(ep, weeks))
        bad = [BAD_FLAGS[f] for f in comp.flags if f in BAD_FLAGS]
        if bad:
            case.reject(ep.id, "; ".join(bad), by)
        else:
            case.accept(ep.id, comp.id, "the territory moved away from clean control territories while the episode "
                        "was active, and not before it", by)
