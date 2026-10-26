# Decision log

Decisions are recorded when they are made, with the alternatives considered. Later entries may
refine earlier ones; nothing is deleted.

| ID | Date | Decision | Alternatives considered | Why |
|---|---|---|---|---|
| D-001 | 2026-10-26 | Python 3.11+ with pandas/numpy/PyYAML, a stdlib `argparse` CLI, SQLite for SQL verification, pytest | Spark/DuckDB; web framework | Installs anywhere with `pip`; volumes (≈1M rows in total) fit comfortably in memory; SQLite lets tests prove the SQL seed loads with foreign keys enforced |
| D-002 | 2026-10-26 | "Short-term" = 13-week (91-day) horizon, daily grain, weekly buckets for accuracy reporting | 30/60/90-day horizons | The 13-week cash-flow forecast is the standard treasury instrument for short-term liquidity |
| D-003 | 2026-10-26 | Actuals run 2026-01-01 → 2026-09-30; weekly historical forecast runs from `FCAST-2026-01-01-001`; a live run as of 2026-10-01 | Full calendar year of actuals | Older runs can be back-tested against actuals while the live run looks forward like a real forecast |
| D-004 | 2026-10-26 | Five currencies: USD (reporting), EUR, GBP, INR, JPY | Majors only | JPY has zero decimal places, which gives a natural rounding boundary case |
| D-005 | 2026-10-26 | Money is held as integer minor units; rounding is half-to-even; exports use fixed-decimal strings | Floats; `Decimal` objects | Reconciliation must be exact (`opening + ledger = closing`); integers are exact and fast |
| D-006 | 2026-10-26 | Every record carries a business date and a `recorded_at` knowledge timestamp; forecast runs only read records recorded before their knowledge cutoff | Snapshot copies of the data per run | Makes every run reproducible after new data arrives and makes look-ahead leakage detectable from lineage |
| D-007 | 2026-10-26 | History is append-only: status changes are event rows, current status is derived; SQLite triggers block UPDATE/DELETE on history tables | Mutable status columns | Requirement: "persist state changes as explicit records/events; do not overwrite history" |
| D-008 | 2026-10-26 | One YAML data dictionary generates the Markdown dictionary, the SQL DDL and the structural validators | Hand-written docs and DDL | Docs, DDL and checks cannot drift apart |
| D-009 | 2026-10-26 | Forecast = rule-based projection of scheduled items plus a weekly run-rate for small flows; no ML | Statistical/ML forecasting | Every number must trace back to source IDs so that variance stays explainable |
| D-010 | 2026-10-26 | Commit the starter dataset in every format; for the full dataset commit the manifest, checksums, ground truth and reports and regenerate the bulk files with one command | Commit everything; Git LFS | Full CSV + JSON + SQL is several hundred MB |
| D-011 | 2026-10-26 | Actors are synthetic users with roles; CLI actions take `--as-user`; a permission matrix and four-eyes approval are enforced | Real authentication | Real auth is out of scope, but role rules and the audit trail are still demonstrable |
| D-012 | 2026-10-26 | No external data; all names are fictional and there is no personal data | Seeding FX from public reference rates | Removes licensing and privacy risk; FX starting levels are round illustrative numbers |
| D-013 | 2026-10-26 | Separate git repository for this folder, repo-local configuration only | — | The parent folder is also a git repository; the project must never pick up files outside it |
