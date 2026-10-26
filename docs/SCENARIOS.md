# Liquidity scenarios

A scenario is **nothing but a list of documented assumptions**, stored as data
(`liquidity_scenario`, `scenario_assumption`, linked by the bridge `scenario_assumption_link`).
The engine has no scenario-specific code paths: every scenario of a run starts from the same
frozen snapshot and applies its assumptions in `apply_order`.

## Versions in force

| Scenario | Effective | Assumptions |
|---|---|---|
| `SCN-BASE-V01` | from 2026-01-01 | none: latest known dates and amounts, FX at the cutoff rate |
| `SCN-DELAY-V01` | from 2026-01-01 | ASM-0001..0004 |
| `SCN-STRESS-V01` | 2026-01-01 → 2026-05-31 (retired) | ASM-0001..0009 |
| `SCN-STRESS-V02` | from 2026-06-01, supersedes V01 | ASM-0001..0008 and ASM-0010 (recalibrated after the May GBP shock) |

A run uses the versions effective on its cutoff date (`forecast_run_scenario` records which).

## Assumptions

| ID | Parameter | Applies to | Value | Rationale |
|---|---|---|---|---|
| ASM-0001 | AR_DELAY_DAYS | receivables from tier A customers | +0 days | tier A pays on time even in a downturn |
| ASM-0002 | AR_DELAY_DAYS | tier B | +7 days | stretches by a week |
| ASM-0003 | AR_DELAY_DAYS | tier C | +21 days | stretches by three weeks |
| ASM-0004 | AR_DELAY_DAYS | tier D | +45 days | stretches by six weeks |
| ASM-0005 | AR_COLLECTION_RATE | tier C | × 0.90 | 10% not collected in the horizon |
| ASM-0006 | AR_COLLECTION_RATE | tier D | × 0.60 | 40% not collected in the horizon |
| ASM-0007 | AP_TIMING_SHIFT_DAYS | supplier payments | −5 days (not before the cutoff) | suppliers demand earlier payment |
| ASM-0008 | RUN_RATE_INFLOW_FACTOR | small operating receipts | × 0.85 | weaker trading |
| ASM-0009 | FX_SHOCK_PCT | every non-USD currency | −8% (USD value) | USD appreciation |
| ASM-0010 | FX_SHOCK_PCT | every non-USD currency | −10% (USD value) | recalibrated shock |

Items pushed beyond the 13-week horizon by a delay drop out of the projection - that is how a
delay reduces liquidity inside the horizon.

## How "scenarios differ only by documented assumptions" is proved

1. **Strip test** (`tests/test_engine.py::test_scenario_without_its_assumptions_equals_base`):
   remove a scenario's assumptions and its projection becomes byte-identical to base.
2. **Filter test** (`test_every_changed_item_matches_a_documented_assumption`): every item whose
   date or amount differs from base matches the filter of an assumption that changes that field.
3. **Exact attribution** (`scenario_assumption_effect`, validator check `A-SCN-attribution`):
   assumptions are applied one at a time; each row records how many items it changed, its effect
   on the horizon's net flow and on the group's lowest projected cash. The effects add up exactly
   to the scenario's difference from base for every run. The live run's table is in
   `data/<profile>/reports/liquidity_outlook.md`.
4. **Back-test**: the same scenarios are compared with actuals; the delayed-receipt scenario is
   closer than base in weeks 2-4, which is where customer delays bite
   (`reports/evaluation.md`).
