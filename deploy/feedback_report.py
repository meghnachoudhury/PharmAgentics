"""Summarize UAT feedback (core-008): the session ratings and the platform questionnaire.

    uv run python deploy/feedback_report.py [--state-dir DIR] [--out report.md] [--csv DIR]

Reads the documents the app stored (the local state folder, default local/state or PHARMAGENTICS_STATE_DIR) and prints a
markdown report: sessions rated good, fine or bad by persona, thumbs up and down on answers (with every downvote), the System Usability Scale score, per-question means, the
net promoter score and every written answer. --csv also writes pulses.csv, votes.csv and survey.csv for a spreadsheet. For the cloud
copy run `uv run python deploy/gcp.py feedback --project pharmagentics --account <you>`, which downloads the bucket's
feedback/ folder first and then runs this. Nothing here sends anything anywhere.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pharmagentics.api import feedback, store  # noqa: E402

PULSE_COLUMNS = ["ts", "session", "user", "rating", "personas", "where", "ref", "comment"]
VOTE_COLUMNS = ["ts", "user", "personas", "lane", "ref", "view", "vote", "engine", "data_version", "comment"]


def _write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:  # utf-8-sig: Excel reads it correctly
        writer = csv.writer(stream)
        writer.writerow(header)
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Summarize UAT feedback.")
    ap.add_argument("--state-dir", type=Path, default=Path(os.environ.get("PHARMAGENTICS_STATE_DIR", ROOT / "local" / "state")))
    ap.add_argument("--out", type=Path, help="write the markdown report here instead of printing it")
    ap.add_argument("--csv", type=Path, metavar="DIR", help="also write pulses.csv, votes.csv and survey.csv into this folder")
    a = ap.parse_args(argv)
    if not a.state_dir.is_dir():
        print(f"No state folder at {a.state_dir}: nothing has been stored there yet.", file=sys.stderr)
        return 1

    q = feedback.questionnaire()
    backend = store.LocalBackend(a.state_dir)
    pulses, surveys = feedback.load_feedback(backend)
    votes = feedback.load_votes(backend)
    report = feedback.to_markdown(feedback.summarize(pulses, surveys, q, votes), q)
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(report, encoding="utf-8")
        print(f"Report written to {a.out}")
    else:
        print(report)

    if a.csv:
        a.csv.mkdir(parents=True, exist_ok=True)
        _write_csv(a.csv / "pulses.csv", PULSE_COLUMNS,
                   [[p["ts"], p["session"], p["user"], p["rating"], "/".join(p["personas"]), p["where"], p.get("ref") or "",
                     p.get("comment") or ""] for p in sorted(pulses, key=lambda d: d["ts"])])
        _write_csv(a.csv / "votes.csv", VOTE_COLUMNS,
                   [[v["ts"], v["user"], "/".join(v["personas"]), v["lane"], v["ref"], v["view"], v["vote"], v.get("engine") or "",
                     v.get("data_version") or "", v.get("comment") or ""] for v in sorted(votes, key=lambda d: d["ts"])])
        item_ids = [i["id"] for i in feedback.items(q)]
        _write_csv(a.csv / "survey.csv", ["user", "ts", "version", "personas", "sus", *item_ids],
                   [[s["user"], s["ts"], s["version"], "/".join(s["personas"]), "" if s["sus"] is None else s["sus"],
                     *(("; ".join(v) if isinstance(v, list) else v) if (v := s["answers"].get(i)) is not None else "" for i in item_ids)]
                    for s in sorted(surveys, key=lambda d: d["ts"])])
        print(f"CSV files written to {a.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
