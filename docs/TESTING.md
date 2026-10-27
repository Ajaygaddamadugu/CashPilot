# Testing approach

Three layers of evidence, from fastest to broadest:

1. **Unit and acceptance tests** (`pytest`, about 5 minutes): run against the starter profile, which uses the
   same generator and engine as the full profile.
2. **The validation suite** (`cashpilot validate`): 300+ checks on any dataset; PASS / EXPECTED /
   FAIL against the ground truth. Runs automatically inside `cashpilot all`.
3. **Evaluation and reproducibility** (`cashpilot all`, `cashpilot repro-check`): detection
   precision/recall, forecast accuracy, and two independent regenerations compared file by file.

CI (`.github/workflows/ci.yml`) runs the tests and the starter reproducibility check on Ubuntu
and Windows, and compares the generated checksums with the committed `data/starter/manifest.json`.

## What each test file proves

| File | Proves |
|---|---|
| `test_core.py` | Half-to-even rounding in minor units (JPY has no decimals), exact text round-trips, USD conversion, business calendar, the brief's ID formats, independent seeded streams |
| `test_schema.py` | All nine core entities exist; every FK points at a primary key; patterns compile; DDL loads in SQLite; the append-only trigger fires; the committed data dictionary is up to date |
| `test_generator.py` | Exact volumes; every FK resolves; IDs match patterns; account IDs embed their entity; statements reconcile with the ledger; transfers net to zero; ledger IDs follow posting order |
| `test_engine.py` | Daily balances roll forward and consolidate; forecast roll-forward; **scenario without its assumptions = base**; **every changed item matches an assumption**; effects sum exactly; **re-running a run reproduces its hashes**; **post-cutoff data cannot change an old run**; lineage is as-of |
| `test_anomalies.py` | Ground truth lives outside the dataset; injected counts follow the profile; injection touches only labelled records; deterministic rules find exactly the injected anomalies; in-tolerance duplicates found with the right decisions; negative controls never flagged; **detection is identical without the ground truth** |
| `test_workflow.py` | Leaky runs superseded by approved as-of re-runs; live forecast approved by a different person; processing only appends history; permissions, illegal transitions and terminal states enforced and audited; variance residual is zero |
| `test_validation.py` | Clean baseline has 0 violations; final dataset has no unexpected violations and every check category ran; a corrupted row is reported as FAIL |
| `test_export.py` | CSV round trip is lossless; JSON mirrors CSV with exact decimals; SQL seed loads with FKs and append-only triggers; manifest covers every file with correct SHA-256 and no timestamps; stored runs are re-created exactly from exported files; same seed → same bytes, other seed → different data |
| `test_fx_positions.py` | **Hand-calculated** multi-currency arithmetic on a micro dataset: half-even rounding, JPY without decimals, inverse and cross rates; the staleness rule at its boundaries (OK / FALLBACK at 1-3 missing fixings / MISSING at 4, weekends, nothing known yet); a rate recorded after the cutoff instant is invisible; daily roll-forward; USD values at each day's rate; a missing rate leaves the value empty (not zero) and flags the entity total INCOMPLETE; totals never add local amounts of different currencies |
| `test_forecast_logic.py` | **Hand-calculated** projection of four receipts/payments: daily balances, buffer breaches (equal to the buffer is not a breach), excluded items never reach the projection, a delayed receipt moves to its new date and the cash is not lost, a receipt delayed past the horizon leaves the window but stays an item, collection haircuts round half-even, supplier timing never precedes the cutoff, FX shocks change foreign balances and flows but not USD, restricted cash is reported but not available |
| `test_metrics.py` | Precision / recall / F1, decision accuracy, negative controls, WAPE and bias, balance MAPE (including skipping actuals with missing FX) on tiny fixtures with answers worked out by hand |
| `test_cli.py` | Every read-only command's output; forecast then four-eyes approval (analyst refused, reviewer allowed); illegal transitions refused and history unchanged; account holders denied and audited; clean errors (exit 2) for a missing dataset, a malformed date, an unknown profile and an unknown command |
| `test_dashboard_data.py` | The dashboard's figures reconcile with the engine: overview = entity positions, exposure = consolidated total, forecast series = sum of entity positions, **scenario items reproduce the engine's daily flows to the cent in every scenario**, run differences carry reasons, exception traces have rule/decision/history/evidence, the reproducibility check passes for clean runs and fails for the look-ahead run, cache signatures change with the files |
| `test_dashboard_explorer.py` | The explorer, *Start here* and plain-language layers: for every account opening balance + flows = the stored closing balance, ledger filtering and major units, entity / account master data and lifecycle history, invoice and bill lists agree with their events, customers pay later the riskier they are, dataset scale vs the brief, acceptance criteria read from saved evidence (and "Not recorded" without it), edge cases and actors counted from the data, **every code the engine can produce has a plain explanation**, every run-comparison reason is explained |
| `test_dashboard_app.py` | Headless run of the real Streamlit app: all nine tabs, every scenario, run and company filter, all three explorer sections (and that the ledger check agrees), *Start here* content, an exception trace, the reproducibility button, the "no dataset" and "not processed" messages, no `None` or mixed-type cells, and that nothing in the dataset is written |

## Acceptance criteria → automated proof

| Criterion | Proof |
|---|---|
| Daily balances reconcile | `test_engine::test_daily_positions_roll_forward_and_match_the_ledger`; validator `A-STM-*`, `A-POS-*`; `R-RECON-001` fires only on labelled breaks |
| Scenarios differ only by documented assumptions | `test_engine::test_scenario_without_its_assumptions_equals_base`, `::test_every_changed_item_matches_a_documented_assumption`, `::test_assumption_effects_add_up_to_the_scenario_difference`; validator `A-SCN-attribution` |
| Forecasts are reproducible | `test_engine::test_rerunning_a_stored_run_reproduces_its_hashes`, `::test_data_recorded_after_the_cutoff_does_not_change_an_old_run`; `test_export::test_stored_runs_are_recreated_exactly_from_the_exported_files`; `cashpilot repro-check` |
| Actual-vs-forecast variance is explainable | `test_workflow::test_every_variance_is_fully_explained`; validator `A-VAR-explained`, `A-VAR-drilldown` |

## Coverage of normal, boundary, failure and exception cases

| Kind | Cases in the data | Where checked |
|---|---|---|
| Normal | On-time tier-A receipts, scheduled payroll/rent/tax, weekly sweeps, approved weekly forecast versions | validator PASS checks, accuracy metrics |
| Boundary | JPY with zero decimals; FX gaps of exactly 1-3 days (fallback) vs 4-5 days (blocked); a transaction recorded just before vs after the 08:00 knowledge cutoff (`test_data_recorded_after_the_cutoff…` uses cutoff + 1 hour); accounts opened, frozen and closed mid-year (no postings outside the active window); an entity acquired on 2026-04-01 (in scope only from its first cutoff); items rolled to the last horizon day; duplicates exactly at the 3-day tolerance vs 5-6 days | `R-FX-001` decisions, `D-LED-active`, horizon checks, sub-type recall |
| Failure (injected) | Five labelled edge cases with variants: bank-only charge, rejected payment, short/long FX gaps, exact/fuzzy/hard duplicates, currency mismatch/unconverted amount, look-ahead runs | `test_anomalies.py`, evaluation report |
| Exception paths | Escalation and waiver of blocked FX conversions; supersession of leaky runs; rejected legacy run re-run as v002; denied cross-entity access; refused approval by the wrong role; refused illegal transitions | `test_workflow.py`, `audit_event`, `exception_event` |
| Negative controls | Legitimate look-alikes labelled `NO_ISSUE` | `test_negative_controls_are_not_flagged`; 0 flagged at both scales |

## Running

```bash
pip install -r requirements-dev.txt && pip install -e .
pytest                      # about 5 minutes
cashpilot all --profile starter --out out/check   # then compare out/check/manifest.json with data/starter/manifest.json
cashpilot repro-check --profile starter           # two fresh runs, every checksum compared
```
