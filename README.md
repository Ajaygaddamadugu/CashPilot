# CashPilot

[![CI](https://github.com/Ajaygaddamadugu/CashPilot/actions/workflows/ci.yml/badge.svg)](https://github.com/Ajaygaddamadugu/CashPilot/actions/workflows/ci.yml)

**Multi-entity cash consolidation and 13-week liquidity forecasting under scenarios**, built on a
reproducible synthetic treasury dataset whose ground truth is known.

CashPilot consolidates daily bank balances for a 30-company group (150 accounts, five
currencies), projects every known cash flow 13 weeks ahead under base, delayed-receipt and stress
scenarios, keeps every forecast version, compares each one with what actually happened and
explains the difference to the cent. It audits its own inputs, raises exceptions with explicit
decisions and routes them through a role-based workflow with four-eyes approval and an
append-only history.

## Results at a glance (full profile, seed 20261022)

| | |
|---|---|
| Volumes | 30 entities, 150 bank accounts, **100,000** ledger entries, **20,000** forecast items, 5 currencies, ~1.2 M rows in 34 tables |
| Data quality | Clean baseline: **0** violations. Final dataset: every validator finding is a labelled anomaly - see [validation summary](data/full/validation_summary.md) |
| Edge-case detection | Balance breaks, FX gaps, mixed currency, look-ahead runs: **100%** precision and recall. Duplicates: 100% within the matching tolerance, 87% overall (hard cases by design). **0 of 35** negative controls flagged - [evaluation](data/full/reports/evaluation.md) |
| Forecast | Group cash-balance error (MAPE) **1.6%** in week 1, 3.1% in weeks 2-4, 6.6% in weeks 5-13; variance explained with **zero residual** on 43,147 entity-weeks |
| Liquidity outlook | As of 2026-10-01: group available cash ≈ USD 690 M; in the stress case it bottoms at ≈ USD 621 M and 13 entities need intra-group funding - [outlook](data/full/reports/liquidity_outlook.md) |
| Interface | Optional read-only web dashboard (Streamlit), written for non-programmers: a *Start here* guide that shows the brief's acceptance criteria and edge cases, cash and FX exposure, companies / accounts / bank transactions / invoices, forecasts and scenarios, cash-flow drivers, exceptions with traceable evidence, forecast vs actual, audit and exports - [docs/DASHBOARD.md](docs/DASHBOARD.md) |
| Reproducibility | Two independent regenerations, every file byte-identical - [report](data/full/reproducibility.md). CI regenerates the starter data on Ubuntu (Python 3.12) and Windows (Python 3.13) and gets the same bytes as the committed bundle |

## Quick start

Requirements: Python 3.11 or newer (developed on 3.13, CI on 3.12) and git.

```bash
git clone https://github.com/Ajaygaddamadugu/CashPilot.git
cd CashPilot
python -m venv .venv
# Windows:      .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements-dev.txt     # exact pins: checksums depend on them
pip install -e . --no-deps

pytest                                   # 147 tests, about 5 minutes (the dashboard tests skip without Streamlit)
cashpilot all --profile starter --out out/starter
```

`cashpilot all` generates the data, validates the clean baseline, injects the labelled edge cases,
runs CashPilot (positions → audit → exceptions → remediation → live forecast → actual vs
forecast), validates, evaluates against the ground truth and exports everything. The starter
profile takes well under a minute; `--profile full` builds the full-scale dataset in a few minutes
(~0.6 GB in CSV + JSON + SQL).

## Open the dashboard (optional)

```bash
pip install -r requirements-dashboard.txt     # the core pins first, then Streamlit
pip install -e . --no-deps
cashpilot dashboard                           # http://localhost:8501, on the committed data/starter
```

Start on the **Start here** tab. The dashboard is read-only and reuses the engine; see [docs/DASHBOARD.md](docs/DASHBOARD.md) for the nine tabs, what is tested and the limits.

![Forecast tab](docs/screenshots/04-forecast.png)

## Verify the key behaviour

| What | How |
|---|---|
| Same data, byte for byte | compare `out/starter/manifest.json` with the committed [`data/starter/manifest.json`](data/starter/manifest.json), or run `cashpilot repro-check --profile starter` |
| Daily balances reconcile | `out/starter/validation_summary.md`: `A-STM-*`, `A-POS-*` PASS; `R-RECON-001` finds only the labelled breaks |
| Scenarios differ only by documented assumptions | `pytest tests/test_engine.py -k scenario`; the assumption-effect table in `out/starter/reports/liquidity_outlook.md` |
| Forecasts are reproducible | `pytest tests/test_engine.py -k "rerunning or recorded_after"` and `tests/test_export.py -k recreated` |
| Variance is explainable | `cashpilot explain --data out/starter --run FCAST-2026-03-12-001 --entity ENT-000002 --week 3` |
| Edge cases and ground truth | `cashpilot exceptions --data out/starter`; labels in `out/starter/ground_truth/ground_truth.csv` (also `.json`); scores in `out/starter/reports/evaluation.md` |
| Roles and audit | the commands in [docs/ACTORS_WORKFLOW.md](docs/ACTORS_WORKFLOW.md#try-it) |

A guided tour with talking points is in [docs/WALKTHROUGH.md](docs/WALKTHROUGH.md).

## Commands

| Command | Purpose |
|---|---|
| `cashpilot all --profile starter\|full [--seed N] [--out DIR]` | the whole pipeline |
| `cashpilot repro-check --profile starter\|full` | regenerate twice and compare every checksum |
| `cashpilot generate`, `run`, `validate`, `evaluate`, `export` | the pipeline step by step on a dataset folder |
| `cashpilot forecast --data DIR --cutoff YYYY-MM-DD --as-user USR-…` | create a CashPilot forecast version |
| `cashpilot run-event`, `exceptions`, `exception`, `view-entity`, `explain` | act as an analyst, reviewer or account holder (permission-checked, audited) |
| `cashpilot docs` | regenerate the data dictionary from `schema/dictionary.yaml` |
| `cashpilot dashboard [--data DIR] [--port N]` | read-only web dashboard (optional Streamlit extra) |

Configuration lives in [`src/cashpilot/profiles/`](src/cashpilot/profiles): volumes, calendar,
policies (FX staleness tolerance, materiality, overdue rules) and anomaly counts. `starter` and
`full` use the same generator; only the numbers differ.

## What is in the repository

```
src/cashpilot/
  core/        money (integer minor units), business calendar, IDs, seeded RNG streams, profiles
  schema/      dictionary.yaml - single source for docs, SQL DDL and structural validation
  generate/    master data, documents, ledger simulation, anomaly injection, legacy forecast history
  engine/      FX rule, positions, forecast runs, workflow, actual-vs-forecast, orchestration
  quality/     detectors and the validation suite
  evaluate/    metrics against ground truth, reproducibility check
  export/      CSV / JSON / SQL bundle and manifest        report/  Markdown reports
  dashboard/   Streamlit-free data layer + the Streamlit app (optional extra)
data/starter/  the starter dataset in every format (+ ground truth, reports, manifest)
data/full/     full-scale manifest, ground truth, validation summary and reports (bulk files regenerate)
docs/          design, decisions, rules, data dictionary, ERD, scenarios, workflow, variance method,
               testing, limitations, provenance, walkthrough, requirements traceability
tests/         147 tests               prompts/  prompt history          AI_USAGE.md          scripts/  helpers
```

## Documentation

| Read this | For |
|---|---|
| [docs/DESIGN.md](docs/DESIGN.md) | the problem, architecture, time model, key decisions and trade-offs |
| [docs/REQUIREMENTS_TRACEABILITY.md](docs/REQUIREMENTS_TRACEABILITY.md) | every point of the brief → implementation → evidence |
| [docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md) · [docs/ERD.md](docs/ERD.md) · [docs/ID_CONVENTIONS.md](docs/ID_CONVENTIONS.md) | the data model |
| [docs/RULES.md](docs/RULES.md) · [docs/SCENARIOS.md](docs/SCENARIOS.md) · [docs/ACTORS_WORKFLOW.md](docs/ACTORS_WORKFLOW.md) · [docs/VARIANCE_METHOD.md](docs/VARIANCE_METHOD.md) | business, detection and workflow rules |
| [docs/TESTING.md](docs/TESTING.md) · [docs/LIMITATIONS.md](docs/LIMITATIONS.md) · [docs/PROVENANCE.md](docs/PROVENANCE.md) | how we know it works, what it does not do, lawful use |
| [docs/DASHBOARD.md](docs/DASHBOARD.md) | the web dashboard: screens, data sources, guarantees, limits, screenshots |
| [docs/DECISION_LOG.md](docs/DECISION_LOG.md) | decisions with alternatives, in the order they were made |
| [AI_USAGE.md](AI_USAGE.md) · [prompts/PROMPT_HISTORY.md](prompts/PROMPT_HISTORY.md) | how AI was used, and the prompts |

All data is synthetic; no external or personal data was used ([provenance](docs/PROVENANCE.md)).
