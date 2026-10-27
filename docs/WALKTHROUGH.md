# Walkthrough (about 10 minutes)

A script for presenting CashPilot. Commands assume the virtual environment is active and run from
the repository root. Work on a copy so the committed bundle stays untouched:

```bash
cashpilot all --profile starter --out out/demo
```

## 1. The problem and the shape of the answer (1 min)

* A 30-entity group, 150 accounts, five currencies. Treasury needs a 13-week view of liquidity
  per entity and for the group, under base, delayed-receipt and stress scenarios.
* Two halves: a **synthetic data factory** whose truth is known (Steps 1-10 of the brief) and the
  **CashPilot engine** that consolidates, forecasts, audits and explains.
* Show [docs/DESIGN.md](DESIGN.md) (architecture diagram) and the requirement-by-requirement
  [REQUIREMENTS_TRACEABILITY.md](REQUIREMENTS_TRACEABILITY.md).

## 2. Data you can trust (2 min)

* One YAML data dictionary drives the docs, the SQL DDL and the validators:
  [DATA_DICTIONARY.md](DATA_DICTIONARY.md), [ERD.md](ERD.md).
* Outcomes come from rules, not random labels - show
  `out/demo/reports/data_profile.md`: lateness grows with customer risk tier; write-offs only for
  tiers C/D; realised FX volatility matches the configuration.
* The baseline is validated **before** any anomaly is injected: `out/demo/validation_summary.md`
  starts with "Clean baseline … 0 violations".
* Exact volumes at full scale: `data/full/manifest.json` → `ledger_entry` 100,000 rows,
  `cash_flow_forecast` 20,000.

## 3. The five edge cases and the ground truth (2 min)

```bash
cashpilot exceptions --data out/demo --limit 12
```

* Each exception names its rule and the decision taken (see [RULES.md](RULES.md)).
* `out/demo/ground_truth/ground_truth.csv` is separate from the data. Detection never reads it
  (test: `test_detection_never_reads_the_ground_truth`); it is only joined afterwards to score the
  detectors - `data/full/reports/evaluation.md`: 100% on four edge cases, 87% recall on duplicates
  because some are deliberately re-keyed outside the matching tolerance, 0 negative controls flagged.

## 4. A forecast and its scenarios (2 min)

```bash
cashpilot forecast --data out/demo --cutoff 2026-10-01 --as-user USR-0003 --purpose LIVE --at "2026-10-02 08:00"
```

* The run reads only what was recorded before 08:00 on the cutoff; its lineage and hashes are
  stored. Show `out/demo/reports/liquidity_outlook.md`: lowest group cash per scenario, entities
  below buffer, and the table of what each documented assumption changed - the effects add up
  exactly to each scenario's difference from base.

## 5. The exception path: a forecast that saw the future (1.5 min)

```bash
cashpilot exceptions --data out/demo --type LOOKAHEAD_LEAKAGE
```

* A legacy run re-generated a week late used data recorded after its cutoff. Lineage proves it
  (`R-LEAK-001`). The fix is an as-of re-run that supersedes it - nothing is edited: open
  `out/demo/csv/forecast_run.csv` and `forecast_run_event.csv` and follow the `SUPERSEDED` event
  to its replacement.

## 6. Roles, four-eyes and audit (1 min)

```bash
cashpilot run-event --data out/demo --run FCAST-2026-10-01-002 --event SUBMITTED --as-user USR-0003 --at "2026-10-02 09:00"
cashpilot run-event --data out/demo --run FCAST-2026-10-01-002 --event APPROVED --as-user USR-0003 --at "2026-10-02 10:00"   # refused: analyst
cashpilot run-event --data out/demo --run FCAST-2026-10-01-002 --event APPROVED --as-user USR-0005 --at "2026-10-02 11:00"   # risk reviewer
cashpilot view-entity --data out/demo --entity ENT-000002 --as-user USR-0007                                                 # denied: other entity
```

Every attempt, allowed or denied, is in `audit_event.csv`.

## 7. Was the forecast right, and why not? (1 min)

```bash
cashpilot explain --data out/demo --run FCAST-2026-03-12-001 --entity ENT-000002 --week 3
```

* Variance is split into timing, amount, FX, new business after the cutoff, unforecasted,
  not realised, run-rate and data-quality drivers with **zero residual** ([VARIANCE_METHOD.md](VARIANCE_METHOD.md)),
  and each driver drills down to forecast items and ledger postings.

## 8. Reproducibility and honesty (0.5 min)

* `data/full/reproducibility.md`: two independent regenerations, every file byte-identical.
* [LIMITATIONS.md](LIMITATIONS.md) and [AI_USAGE.md](../AI_USAGE.md).

## 9. The same story in the browser (optional, 2 min)

```bash
cashpilot dashboard --data out/demo
```

* **Forecast** tab: the three scenarios on one chart, and the assumptions table whose effects add up to the difference from base.
* **Exceptions** tab: pick the look-ahead exception and show the inputs the run saw from the future and the run that superseded it.
* **Audit & exports** tab: press *Verify reproducibility* on the live run (reproduced) and on `FCAST-2026-05-21-001` (not reproducible).
* Everything is read-only; actions stay in the CLI where permissions and four-eyes exist ([DASHBOARD.md](DASHBOARD.md)).

## Likely questions

| Question | Short answer |
|---|---|
| Why rule-based forecasting? | Every number must trace back to IDs and the variance must be explainable exactly; the attribution shows where a pipeline model would add most (new business after cutoff). |
| How do you prove scenarios differ only by assumptions? | Strip a scenario's assumptions and it is byte-identical to base; every changed item matches an assumption filter; per-assumption effects sum exactly. |
| How is look-ahead detected? | Each run stores the recorded-at time of every input; any input recorded after the knowledge cutoff is a leak. Re-running a clean run reproduces its hashes, re-running a leaky one does not. |
| Why are some metrics 100%? | The deterministic rules are exact for well-defined cases; that is a correctness check. The hard duplicates and the negative controls keep the evaluation honest. |
| What would you build next? | A sales/purchase pipeline forecast for new business, configurable tolerances per entity, and a database-backed workflow with real authentication. |
