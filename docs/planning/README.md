# Planning sources

The Google Docs in the Drive folder **Consolidated 10/22** are the masters. The Markdown files here are copies taken on 2026-10-23, checked against the masters on 2026-10-29 (only the System Architecture caption had changed), so that coding agents (Antigravity, Claude Code) can read them. When a master changes, update it first, then refresh its copy here, then the specs that cite it.

## Precedence

From the System Architecture (§1). A higher source wins.

1. The Proposal.
2. Each use case's personas and evaluation pack.
3. The System Architecture, for everything shared or cross-agent.
4. Each agent's own architecture doc, for the internals of its lane.

The user stories anchor every acceptance scenario. They restate the persona questions on real weeks of the data release, so they rank with the personas.

## Files

| Copy here | Master in Drive | Owner | Date | Use |
| :- | :- | :- | :- | :- |
| [system-architecture.md](system-architecture.md) | [PharmAgentics — System Architecture (SoT)](https://docs.google.com/document/d/1MC9rxg52WKnZlddxTl22T7jAyd6yXfkBlwg7Xa--KQc/edit) | Michael | Oct 22 | Shared platform, the spine, contracts, vocabulary, S1 to S16 |
| [briefing-architecture.md](briefing-architecture.md) | [Architecture 10/21](https://docs.google.com/document/d/1wDU3zzejn3s29sPopm0owkisYW0dRC6Omdox52fWV7A/edit) | Michael, Meghna | Oct 21 | Briefing lane internals, run states, A1 to A17 |
| [briefing-personas.md](briefing-personas.md) | [Personas - 10/21](https://docs.google.com/document/d/17EPYkCtESC3Up-P6TN8UeuOFluzWHv5vVnO3nUpMUQo/edit) | Michael | Oct 21 | P1 to P4, questions P1-Q1 to P4-Q6 |
| [briefing-evaluation-pack.md](briefing-evaluation-pack.md) | [Evaluation Pack - 10/21](https://docs.google.com/document/d/1ylxQmnVx3Oz-C4li19KteA9rbkl1hvHzHpHqve6AuuE/edit) | Michael | Oct 21 | EV-1.1 to EV-9.4, case taxonomy, open items 1 to 19 |
| [user-stories.md](user-stories.md) | [User stories](https://docs.google.com/document/d/11NDXbYbC3GZB7oHj24wXPUTVjNcjmCbi_GSWB21Un40/edit) | Michael | Oct 22 | 42 Given/When/Then stories on real weeks; 24 Briefing, 18 Forecast |
| Not copied | [AALS Project Proposal (PDF)](https://drive.google.com/file/d/1jqXBAv0tGW1YGpO2jfzw55NsHZZpHvPO/view) | All four | Oct 6 | Scope, Magentic pattern, risks |
| Not copied | [Oct 16 - Personas & Eval Design (PDF)](https://drive.google.com/file/d/1X0RyEAHfEfzDER1KByMYugp_TLBDJRCD/view) | Sienna | Oct 16 | Forecast lane: CA, BM, FM; FE-01 to FE-31; TC-01 to TC-12. Owned by the Forecast team; specs cite it by ID only |
| Not copied | [PharmAgentics_System_Architecture.png](https://drive.google.com/file/d/1o8kUFD1bsyn6ItvASjqqXnPuC_hGuiSs/view) | Michael | Oct 22 | System diagram |
| [PharmAgentics_Data_Research_Brief.pptx](PharmAgentics_Data_Research_Brief.pptx) | — | Meghna | Oct 16 | Data world research; sampling model |
| [data-plan-triage.md](data-plan-triage.md) | Course slide, SoT drop 2026-11-11 (`Five-question triage (data plan).png`) | Michael | Nov 11 | Five-question data-plan triage (decision, population, granularity, time, cost and rights); course reference, outside the precedence order |

The Oct 16 `Architecture.docx`, `Personas.docx`, `Evaluation Pack.docx` and `pharmagentics_architecture.png` were removed on 2026-10-23 because the files above supersede them. They remain in git history.

## Forecast lane

Alvin and Sienna own the Forecast personas, evaluation, constitution and specs (System Architecture D3, D5). Their work lives on the `alvin-forecast-explanation` branch until it merges. Shared specs (`specs/core-*`) record what the Forecast lane needs from the platform, and cite FE and TC IDs without restating them.
