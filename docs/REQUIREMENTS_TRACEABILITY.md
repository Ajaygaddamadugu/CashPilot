# Requirements traceability

Every point of the brief, where it is implemented and what proves it. Paths are relative to the
repository root; "validator" refers to check IDs in `validation_summary.md`.

**Status:** all items **Verified** (an automated test, validator check or generated report
demonstrates them).

## A. Business problem and scope

| ID | Requirement | Implementation | Evidence |
|---|---|---|---|
| A1 | Consolidate account balances | `engine/positions.py`: account-day positions rebuilt from the ledger, valued in USD, consolidated per entity (available vs restricted) | `test_engine::test_daily_positions_roll_forward_and_match_the_ledger`; validator `A-POS-*` |
| A2 | Consolidate expected cash flows | `engine/forecast.py`: as-of snapshot of forecast items, revisions, statements and FX per run | `test_engine::test_lineage_only_contains_records_known_before_the_cutoff` |
| A3 | Forecast short-term liquidity under scenarios | 13-week daily projection per entity for base, delayed-receipt and stress | `reports/liquidity_outlook.md`; `test_engine.py` |
| A4 | Expose key decisions and exceptions | Rule catalogue ([RULES.md](RULES.md)); every exception has a rule, severity and decision; every forecast item a `treatment` in run lineage | `exception`, `forecast_run_item`; `test_anomalies.py` |
| A5 | Preserve traceability | Immutable IDs, lineage tables, input/result hashes, append-only events, audit log, manifest | `test_engine::test_rerunning_a_stored_run_reproduces_its_hashes`; `test_export::test_stored_runs_are_recreated_exactly_from_the_exported_files` |
| A6 | Measurable outputs | Detection P/R/F1 and decision accuracy, forecast WAPE/bias, balance MAPE, variance drivers, liquidity metrics, reconciliation rate | `data/full/reports/evaluation.md` |
| A7 | Medium complexity: related entities, conditional rules, ≥ 1 exception path, evaluation metrics | 34 tables; tiered behaviour, roll-forward, staleness, approval and access rules; exception playbook incl. supersession of leaky runs | [RULES.md](RULES.md), [ACTORS_WORKFLOW.md](ACTORS_WORKFLOW.md), `test_workflow.py` |

## B. Actors

| ID | Actor | Implementation | Evidence |
|---|---|---|---|
| B1 | Customer / account holder | `ACCOUNT_HOLDER` per entity: submits manual forecast items, views own entity only | `test_workflow::test_permissions_four_eyes_and_waivers_are_enforced`; `audit_event` DENIED row |
| B2 | Operations analyst | Prepares runs, works and escalates exceptions, prepares remediation re-runs | `forecast_run_event`, `exception_event` |
| B3 | Risk/compliance reviewer | Approves/rejects runs (four-eyes), waives with justification, freezes accounts, approves large bills | `test_workflow::test_live_forecast_is_approved_by_a_different_person` |
| B4 | System administrator | Opens/closes accounts, publishes scenario versions | `bank_account_event`, `liquidity_scenario.created_by` |

## C. Business workflow rules

| ID | Rule | Implementation | Evidence |
|---|---|---|---|
| C1 | Master data first | `generate/pipeline.py`: reference → entities → accounts → counterparties → FX → documents → forecast items → ledger → statements | code order; FK checks pass |
| C2 | Dependent records use valid parent IDs | children built from parent frames | `test_generator::test_every_foreign_key_resolves`; validator `I-FK-*` |
| C3 | Entities/accounts; opening balances and ledger; scheduled AR/AP with expected dates; FX; daily cash positions; base/delayed/stress; forecast versions; actual vs forecast | `generate/master.py`, `documents.py`, `ledger.py`; `engine/positions.py`, `forecast.py`, `compare.py` | tables `bank_account`, `ledger_entry`, `receivable`, `payable`, `currency_rate`, `daily_cash_position`, `liquidity_scenario`, `forecast_run`, `forecast_vs_actual` |
| C4 | State changes as events; never overwrite history | event tables + derived `status_at_end`; workflow appends only; SQLite append-only triggers | `test_workflow::test_processing_only_appends_to_history`; `test_export::test_sql_seed_loads…`; validator `L-*` |
| C5 | Outcomes and labels from documented rules | delays, partials, holds, write-offs by rule (G-*); labels from injection rules (INJ-*) | [RULES.md](RULES.md); `reports/data_profile.md` (lateness by tier) |

## D. Entities and relationships

| ID | Requirement | Implementation | Evidence |
|---|---|---|---|
| D1 | Nine core entities | `legal_entity`, `bank_account`, `ledger_entry`, `cash_flow_forecast`, `receivable`, `payable`, `currency_rate`, `liquidity_scenario`, `forecast_run` | `test_schema::test_every_core_entity_from_the_brief_is_defined` |
| D2 | PK for every entity, FK for every relationship | `schema/dictionary.yaml` → DDL and validator | `test_schema::test_every_foreign_key_points_at_a_primary_key`; validator `S-PK-*`, `I-FK-*` |
| D3 | Cardinality, optionality, effective dates, lifecycle states | generated in [DATA_DICTIONARY.md](DATA_DICTIONARY.md); [ERD.md](ERD.md) | `test_schema::test_committed_data_dictionary_is_up_to_date` |
| D4 | Bridge tables for N:M | `settlement_allocation`, `scenario_assumption_link`, `forecast_run_scenario`, `forecast_run_item` | dictionary "Many-to-many" section |
| D5 | Event history for state changes | `bank_account_event`, `receivable_event`, `payable_event`, `cf_revision`, `forecast_run_event`, `exception_event`, `audit_event` | validator `L-*` (state machines, derived status) |
| D6 | Validate all joins | join-consistency checks | validator `I-JOIN-*`, `I-EMBED-*` |
| D7 | Anomalies labelled, unrelated rows untouched | ground truth keyed by record ID; injection touches only targets | `test_anomalies::test_injection_touches_only_the_labelled_records` |

## E. ID conventions

| ID | Requirement | Evidence |
|---|---|---|
| E1 | `ENT-000001`, `BANKACC-<entity-id>-001`, `LED-2026-00000001`, `CF-2026-000001`, `FCAST-2026-01-01-001` | `test_core::test_id_conventions_from_the_brief`; validator `S-PAT-*` |
| E2 | Zero-padded, immutable, consistent across files | [ID_CONVENTIONS.md](ID_CONVENTIONS.md); validator `I-EMBED-*`, `I-FK-*`; `test_generator::test_account_ids_embed_their_entity` |

## F. Synthetic data generation steps

| Step | Requirement | Implementation | Evidence |
|---|---|---|---|
| 1 | Data dictionary with type, required, allowed values, units, uniqueness, validation rule | `schema/dictionary.yaml` → [DATA_DICTIONARY.md](DATA_DICTIONARY.md) | `test_schema.py` |
| 2 | Parents first, then children and events | generation order (C1) | FK checks |
| 3 | Deterministic IDs and naming | `core/ids.py`; documented sort orders | E1, E2 |
| 4 | 30 / 150 / 100,000 / 20,000 / 5 currencies; delayed receivables, FX movement, large one-offs; fixed seed; scale parameter | `profiles/full.yaml`, `profiles/starter.yaml` (same generator) | validator `V-*`; `data/full/manifest.json`; `test_generator::test_volumes_hit_the_profile_targets_exactly`; `reports/data_profile.md` |
| 5 | Valid baseline first, then labelled edge cases | `generate_baseline` → validate → `inject` | `test_validation::test_clean_baseline_has_no_violations` |
| 6 | Derived values from source records | statements, positions, statuses, totals, forecasts computed | validator `A-*`, `L-*-status` |
| 7 | Separate ground truth, never leaked | `ground_truth/anomalies.csv|json`; detectors cannot see it | `test_anomalies::test_ground_truth_lives_outside_the_dataset`, `::test_detection_never_reads_the_ground_truth`; validator `G-no-labels` |
| 8 | Validation: PK, FK, enums, date ordering, reconciliation, lifecycle, duplicates | `quality/validate.py` | `validation_summary.md`; `test_validation.py` |
| 9 | CSV/JSON/SQL + README, dictionary, generator command, seed, source manifest, validation summary | `export/bundle.py` | `data/starter/`; `test_export.py` |
| 10 | Regenerate twice, compare counts and checksums | `cashpilot repro-check` | `data/starter/reproducibility.md`, `data/full/reproducibility.md`; `test_export::test_same_seed_gives_identical_bytes…`; CI |

## G. Edge cases

| ID | Edge case | Injection | Detection | Evidence |
|---|---|---|---|---|
| G1 | Opening + ledger ≠ closing | INJ-REC-01/02 | R-RECON-001 | evaluation: recall 100% |
| G2 | FX rate missing | INJ-FX-01/02 | R-FX-001 (fallback vs block) | evaluation: recall 100%, decisions 100% |
| G3 | Cash flow counted twice | INJ-DUP-01/02/03 | R-DUP-001/002; excluded by the forecast gate | evaluation: in-tolerance 100%, overall 87% (hard cases by design) |
| G4 | Forecast uses actual after cutoff | INJ-LEAK-01 | R-LEAK-001; remediation re-run | `test_workflow::test_leaky_runs_are_superseded_by_approved_as_of_reruns` |
| G5 | Currency mixed without conversion | INJ-CUR-01/02 | R-CUR-001/002; converted by the gate | evaluation: recall 100% |

## H. Acceptance criteria

| ID | Criterion | Evidence |
|---|---|---|
| H1 | Daily balances reconcile | `test_engine::test_daily_positions_roll_forward_and_match_the_ledger`; validator `A-STM-*`, `A-POS-*`, `R-RECON-001` (only labelled breaks) |
| H2 | Scenarios differ only by documented assumptions | `test_engine::test_scenario_without_its_assumptions_equals_base`, `::test_every_changed_item_matches_a_documented_assumption`, `::test_assumption_effects_add_up_to_the_scenario_difference`; validator `A-SCN-attribution` |
| H3 | Forecasts are reproducible | `test_engine::test_rerunning_a_stored_run_reproduces_its_hashes`, `::test_data_recorded_after_the_cutoff_does_not_change_an_old_run`; `test_export::test_stored_runs_are_recreated_exactly_from_the_exported_files`; repro-check |
| H4 | Actual-vs-forecast variance is explainable | [VARIANCE_METHOD.md](VARIANCE_METHOD.md); `test_workflow::test_every_variance_is_fully_explained`; validator `A-VAR-explained`, `A-VAR-drilldown` |

## I. Evaluation focus

| ID | Focus | Evidence |
|---|---|---|
| I1 | Realistic distributions, meaningful variation | `reports/data_profile.md` |
| I2 | Consistent IDs, valid joins | validator `S-PAT-*`, `I-*` |
| I3 | Dependency/lifecycle consistency | validator `L-*`, `D-*` |
| I4 | Correct derived values, reconciliation | validator `A-*` |
| I5 | Normal, boundary, failure, exception coverage | [TESTING.md](TESTING.md#coverage-of-normal-boundary-failure-and-exception-cases); negative controls |
| I6 | Separate ground truth | F7 |
| I7 | Reproducibility, documentation, lawful provenance | repro reports; `docs/`; [PROVENANCE.md](PROVENANCE.md) |

## J. Submission guidelines

| ID | Guideline | Evidence |
|---|---|---|
| J1 | Working code with install, configure, run, verify steps | [README.md](../README.md) quick start; CI on Ubuntu and Windows |
| J2 | Public repository, meaningful commits | `git log` (one commit per layer, each tested) |
| J3 | LLM use disclosed, prompt history | [AI_USAGE.md](../AI_USAGE.md), [prompts/PROMPT_HISTORY.md](../prompts/PROMPT_HISTORY.md) |
| J4 | Reasoning visible | [DESIGN.md](DESIGN.md), [DECISION_LOG.md](DECISION_LOG.md), [TESTING.md](TESTING.md), [LIMITATIONS.md](LIMITATIONS.md), [WALKTHROUGH.md](WALKTHROUGH.md) |
