# PharmAgentics

Multi-agent AI platform for pharma commercial analytics, where a shared data layer and orchestration power agents for brand-performance briefings, plain-language forecast explanations, payer-access impact analysis (NBRx, abandonment, net price), and HCP segmentation with next-best-action targeting.

The initial data foundation loads 14 supplied synthetic datasets into a persistent
DuckDB database. It preserves missing and duplicate feed artifacts, reports their
evidence, and provides weekly Rx KPIs gated by feed health. Gemini integration
and analytical agent tools are future work.

See [DuckDB first-run instructions](docs/DUCKDB_FIRST_RUN.md) for installation,
data checks, example queries, and tests. Python 3.11+ is required.
