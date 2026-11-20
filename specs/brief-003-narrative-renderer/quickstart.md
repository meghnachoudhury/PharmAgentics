# Quickstart: prove slice 1 works

From the repository root (or the worktree), after `uv sync`.

## 1. Rebuild the database (adds the view)

```powershell
uv run python src/pharmagentics/data/load_duckdb.py
uv run python src/pharmagentics/data/check_duckdb.py
```

Expect: the data version is unchanged (`47bcfd650564`).

## 2. Tests

```powershell
uv run pytest tests/test_projection.py tests/test_memo.py tests/test_tools.py tests/test_mcp_server.py tests/test_agent_build3.py tests/test_briefing_api.py eval/tests
```

Expect: projected national matches the hand calculation (observed ÷ coverage per territory, estimate rule for the rest) in every one of the 104 weeks (SC-011); every brief has the six headings in order; §1 holds its four statements in order; no digit outside a token.

## 3. Golden set

```powershell
uv run python -m eval check
```

Expect: every fact recomputes, including the new P1-Q2 and P3-Q6 facts.

## 4. Read three briefs

```powershell
uv run python -m eval run --system briefing_scripted --lane briefing --stories P1-Q2,P3-Q6,P1-Q3
```

Open the traces in `uv run python -m eval ui`. Expect:

- **P1-Q2 (2026-05-04)**: §1 opens with New England's incomplete feed; projected national 4,491; New England projected at 407 (observed 267, coverage 0.656); least sure is New England; no New England story; §4 lists its reasons.
- **P3-Q6 (2026-07-13)**: §1 notes a restated week; §2 says Mid-Atlantic 2026-04-06 went from 692 to 742 on 2026-07-13; projected national 4,240 with every territory observed; like-for-like states 7 of 8.
- **P1-Q3 (2025-04-21)**: routine week; projected national equals the observed sum; nothing labelled projected; §3 says no material change.

## 5. Gate

```powershell
uv run python -m eval run --system briefing_scripted --lane briefing
uv run python -m eval gate <candidate> <scripted baseline at c15ccde>
uv run python -m eval run --system briefing_agent --lane briefing --model anthropic:claude-haiku-5-5
uv run python -m eval gate <candidate> <agent baseline at c15ccde>
```

Expect: exit 0 for both. Report-only checks (recall, numbers match) may move; say how and why.
