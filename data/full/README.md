# CashPilot dataset — `full` profile

Synthetic treasury data for a 30-entity group, generated with seed **20261022**.

Regenerate byte-for-byte with:

```
cashpilot all --profile full --seed 20261022
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
| `counterparty` | reference | 1,000 | Fictional customers and suppliers. Customer risk tier drives payment behaviour. |
| `currency_rate` | reference | 961 | Daily closing FX rates against USD, one per business day and currency. |
| `scenario_assumption` | reference | 10 | Documented, parameterised assumptions. Scenarios differ only through these rows. |
| `legal_entity` | master | 30 | Companies in the group. One holding company owns every operating entity. |
| `bank_account` | master | 150 | Bank accounts held by the entities. Pool headers concentrate cash per currency. |
| `receivable` | transaction | 8,628 | Customer invoices (accounts receivable) with expected collection dates. |
| `payable` | transaction | 7,059 | Supplier bills and large one-off obligations (accounts payable). |
| `bank_statement` | transaction | 28,603 | Daily statements as reported by the banks (the bank's view of each account). |
| `daily_cash_position` | derived | 40,031 | Actual daily position per account from the ledger, with the bank's view and USD value. |
| `entity_cash_position` | derived | 8,100 | Consolidated actual daily cash per entity in USD. |
| `app_user` | reference | 37 | Synthetic users acting in the workflow. Names are role labels, not people. |
| `liquidity_scenario` | reference | 4 | Versioned liquidity scenarios. A scenario is defined only by its linked assumptions. |
| `scenario_assumption_link` | bridge | 22 | Which assumptions make up each scenario version, in application order. |
| `cash_flow_forecast` | transaction | 20,000 | Expected cash-flow items: subledger feeds, recurring schedules, run-rate estimates and manual submissions. |
| `ledger_entry` | transaction | 100,000 | Booked cash movements (actuals). Positive = inflow, negative = outflow, in account currency. |
| `settlement_allocation` | bridge | 13,591 | How cash postings settle invoices and bills: one transfer may pay several invoices, one invoice may be paid in parts. |
| `bank_account_event` | event | 154 | Account lifecycle history (append-only). |
| `receivable_event` | event | 16,768 | Invoice lifecycle history (append-only). |
| `payable_event` | event | 20,431 | Bill lifecycle history (append-only). |
| `cf_revision` | event | 22,443 | Later changes to forecast items (new date, new amount, settled, cancelled). Items themselves never change. |
| `forecast_run` | history | 46 | Forecast versions. Each run is an immutable 13-week projection as of a cutoff. |
| `forecast_run_event` | event | 187 | Forecast run lifecycle history (append-only). |
| `forecast_run_scenario` | bridge | 135 | Scenarios evaluated in each run. |
| `forecast_run_item` | bridge | 155,521 | Input lineage: every forecast item a run considered, the revision it used and how it was treated. |
| `forecast_run_balance_input` | history | 6,753 | Input lineage: the bank statement each run used as an account's opening balance. |
| `forecast_run_fx_input` | history | 184 | Input lineage: the FX rate each run used per currency. |
| `forecast_position` | history | 364,819 | Run results: projected daily available cash per entity and scenario, in USD. |
| `scenario_assumption_effect` | derived | 571 | Contribution of each assumption to a scenario, applied in order (proves scenarios differ only by documented assumptions). |
| `forecast_vs_actual` | derived | 43,147 | Actual-versus-forecast per run, scenario, entity and week, with the variance split into drivers. |
| `variance_attribution` | derived | 303,378 | Item-level drill-down of the base-scenario variance. |
| `exception` | output | 195 | Exceptions raised by CashPilot rules, each with a rule ID and a decision. |
| `exception_event` | output | 659 | Exception workflow history (append-only). |
| `audit_event` | output | 680 | Every workflow action attempted through CashPilot, allowed or denied. |

## Provenance

Fully synthetic. No external dataset, API or personal data was used. Company, bank and person names are fictional; FX starting levels are round illustrative numbers. ISO 4217 is used only as a public reference for currency codes and decimal places.
