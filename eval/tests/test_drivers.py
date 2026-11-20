"""Driver-recovery scoring (fcst-001): recall, false drivers and the confusion matrix on hand-made rows."""
from eval.harness.drivers import accepted, probes, score


def test_scoring_counts_hits_misses_and_false_drivers():
    rows = [{"expect": ["supply", "competitor"], "got": ["competitor", "supply"]},
            {"expect": ["promotion"], "got": ["access"]},
            {"expect": [], "got": ["promotion"]},
            {"expect": [], "got": []}]
    out = score(rows)
    assert out["metrics"] == {"driver_recall": 0.667, "false_drivers": 2, "exact_set_share": 0.5, "probes": 4}
    cm = out["confusion"]
    assert cm["supply"]["supply"] == 1 and cm["promotion"]["access"] == 1
    assert cm["none"]["promotion"] == 1 and cm["none"]["none"] == 1


def test_a_national_probe_counts_only_broad_drivers():
    report = {"drivers": [{"driver": "competitor", "territory": "ALL"}, {"driver": "promotion", "territory": "SOUTHEAST"}]}
    assert accepted(report, "NATIONAL") == {"competitor"}
    assert accepted(report, "SOUTHEAST") == {"competitor", "promotion"}


def test_the_draft_probes_are_well_formed():
    ps = probes()
    assert len({p["id"] for p in ps}) == len(ps) >= 10
    assert all(set(p["expect"]) <= {"access", "promotion", "supply", "competitor"} for p in ps)
