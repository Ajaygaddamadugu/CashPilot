# CashPilot dataset — `starter` profile

Synthetic treasury data for a 5-entity group, generated with seed **20261022**.

Regenerate byte-for-byte with:

```
cashpilot all --profile starter --seed 20261022
```

## Layout

| Path | Content |
|---|---|
| `csv/` | One CSV per table (UTF-8, `\n` line endings, header row) |
| `json/` | The same tables as JSON arrays; money and rates are exact decimal strings |
| `sql/` | `schema.sql` (DDL with PK/FK/CHECK), `append_only_sqlite.sql`, `seed.sql` |
| `ground_truth/` | Labels of the injected anomalies and negative controls. **Not an input**: never use as a feature |
| `data_dictionary.md` | Every field: type, required, allowed values, units, uniqueness, validation rule |
| `validation_summary.md` | Step 8 checks and their results |
| `reports/` | Evaluation, 13-week liquidity outlook, data profile |
| `manifest.json` | Row counts and SHA-256 checksums of every file |

Validation: **PASS**.

## Tables

| Table | Layer | Rows | Description |
|---|---|---|---|
| `currency` | reference | 5 | ISO 4217 currencies in scope. Minor units drive rounding and formatting. |
| `counterparty` | reference | 130 | Fictional customers and suppliers. Customer risk tier drives payment behaviour. |
| `currency_rate` | reference | 972 | Daily closing FX rates against USD, one per business day and currency. |
| `scenario_assumption` | reference | 10 | Documented, parameterised assumptions. Scenarios differ only through these rows. |
| `legal_entity` | master | 5 | Companies in the group. One holding company owns every operating entity. |
| `bank_account` | master | 25 | Bank accounts held by the entities. Pool headers concentrate cash per currency. |
| `receivable` | transaction | 727 | Customer invoices (accounts receivable) with expected collection dates. |
| `payable` | transaction | 594 | Supplier bills and large one-off obligations (accounts payable). |
| `bank_statement` | transaction | 4,367 | Daily statements as reported by the banks (the bank's view of each account). |
| `daily_cash_position` | derived | 6,101 | Actual daily position per account from the ledger, with the bank's view and USD value. |
| `entity_cash_position` | derived | 1,275 | Consolidated actual daily cash per entity in USD. |
| `app_user` | reference | 11 | Synthetic users acting in the workflow. Names are role labels, not people. |
| `liquidity_scenario` | reference | 4 | Versioned liquidity scenarios. A scenario is defined only by its linked assumptions. |
| `scenario_assumption_link` | bridge | 22 | Which assumptions make up each scenario version, in application order. |
| `cash_flow_forecast` | transaction | 2,000 | Expected cash-flow items: subledger feeds, recurring schedules, run-rate estimates and manual submissions. |
| `ledger_entry` | transaction | 10,000 | Booked cash movements (actuals). Positive = inflow, negative = outflow, in account currency. |
| `settlement_allocation` | bridge | 1,118 | How cash postings settle invoices and bills: one transfer may pay several invoices, one invoice may be paid in parts. |
| `bank_account_event` | event | 28 | Account lifecycle history (append-only). |
| `receivable_event` | event | 1,393 | Invoice lifecycle history (append-only). |
| `payable_event` | event | 1,735 | Bill lifecycle history (append-only). |
| `cf_revision` | event | 2,398 | Later changes to forecast items (new date, new amount, settled, cancelled). Items themselves never change. |
| `forecast_run` | history | 23 | Forecast versions. Each run is an immutable 13-week projection as of a cutoff. |
| `forecast_run_event` | event | 93 | Forecast run lifecycle history (append-only). |
| `forecast_run_scenario` | bridge | 68 | Scenarios evaluated in each run. |
| `forecast_run_item` | bridge | 8,708 | Input lineage: every forecast item a run considered, the revision it used and how it was treated. |
| `forecast_run_balance_input` | history | 518 | Input lineage: the bank statement each run used as an account's opening balance. |
| `forecast_run_fx_input` | history | 92 | Input lineage: the FX rate each run used per currency. |
| `forecast_position` | history | 29,029 | Run results: projected daily available cash per entity and scenario, in USD. |
| `scenario_assumption_effect` | derived | 290 | Contribution of each assumption to a scenario, applied in order (proves scenarios differ only by documented assumptions). |
| `forecast_vs_actual` | derived | 3,322 | Actual-versus-forecast per run, scenario, entity and week, with the variance split into drivers. |
| `variance_attribution` | derived | 15,973 | Item-level drill-down of the base-scenario variance. |
| `exception` | output | 41 | Exceptions raised by CashPilot rules, each with a rule ID and a decision. |
| `exception_event` | output | 137 | Exception workflow history (append-only). |
| `audit_event` | output | 148 | Every workflow action attempted through CashPilot, allowed or denied. |

## Provenance

Fully synthetic. No external dataset, API or personal data was used. Company, bank and person names are fictional; FX starting levels are round illustrative numbers. ISO 4217 is used only as a public reference for currency codes and decimal places.
