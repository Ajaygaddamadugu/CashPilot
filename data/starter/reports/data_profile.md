# Data profile — `starter` dataset

## Row counts

| Table | Rows |
|---|---|
| `currency` | 5 |
| `app_user` | 11 |
| `counterparty` | 130 |
| `currency_rate` | 972 |
| `liquidity_scenario` | 4 |
| `scenario_assumption` | 10 |
| `scenario_assumption_link` | 22 |
| `legal_entity` | 5 |
| `bank_account` | 25 |
| `receivable` | 727 |
| `payable` | 594 |
| `cash_flow_forecast` | 2,000 |
| `ledger_entry` | 10,000 |
| `settlement_allocation` | 1,118 |
| `bank_statement` | 4,367 |
| `bank_account_event` | 28 |
| `receivable_event` | 1,393 |
| `payable_event` | 1,735 |
| `cf_revision` | 2,398 |
| `forecast_run` | 23 |
| `forecast_run_scenario` | 68 |
| `forecast_run_item` | 8,708 |
| `forecast_run_balance_input` | 518 |
| `forecast_run_fx_input` | 92 |
| `forecast_position` | 29,029 |
| `scenario_assumption_effect` | 290 |
| `forecast_run_event` | 93 |
| `daily_cash_position` | 6,101 |
| `entity_cash_position` | 1,275 |
| `exception` | 41 |
| `exception_event` | 137 |
| `audit_event` | 148 |
| `forecast_vs_actual` | 3,322 |
| `variance_attribution` | 15,973 |

## Customer payment behaviour by risk tier (rule-driven)

| Tier | Invoices | Paid | Median days late | Paid > 7 days late | Written off |
|---|---|---|---|---|---|
| A | 144 | 126 | 1.0 | 4.8% | 0 |
| B | 349 | 273 | 8.0 | 53.1% | 0 |
| C | 185 | 147 | 18.0 | 85.7% | 1 |
| D | 49 | 18 | 30.0 | 83.3% | 4 |

## FX movement

| Currency | Realised annual volatility | Configured | Change over the period |
|---|---|---|---|
| EUR/USD | 7.4% | 7.0% | -5.6% |
| GBP/USD | 9.2% | 8.0% | -3.1% |
| INR/USD | 4.1% | 4.0% | -3.4% |
| JPY/USD | 10.1% | 10.0% | -14.1% |

## Ledger

| Entry type | Count |
|---|---|
| OPERATING_RECEIPT | 4,325 |
| OPERATING_PAYMENT | 3,536 |
| AR_RECEIPT | 560 |
| POOL_SWEEP | 550 |
| AP_PAYMENT | 523 |
| BANK_FEE | 200 |
| POOL_FUNDING | 94 |
| FX_CONVERSION | 68 |
| RENT | 42 |
| PAYROLL | 42 |
| INTEREST | 19 |
| TAX | 14 |
| OTHER_RECEIPT | 13 |
| OTHER_PAYMENT | 12 |
| ACCOUNT_CLOSURE | 2 |

Absolute posting amounts by currency (major units):

| Currency | p10 | p50 | p90 | p99 |
|---|---|---|---|---|
| EUR | 1,259 | 5,221 | 66,135 | 1,166,130 |
| GBP | 834 | 5,576 | 122,012 | 472,110 |
| INR | 122,601 | 471,501 | 10,384,503 | 59,940,338 |
| JPY | 222,145 | 857,130 | 11,628,410 | 158,188,725 |
| USD | 1,171 | 6,305 | 177,840 | 1,427,801 |

Postings by weekday: Monday 1,967, Tuesday 1,698, Wednesday 1,754, Thursday 1,667, Friday 2,914.

Large one-off payments: 6 (TAX_SETTLEMENT 2, DEBT_REPAYMENT 2, CAPEX 1, ACQUISITION 1).

Entities by size tier: L 1, M 2, S 2. Accounts by currency: EUR 6, GBP 3, INR 3, JPY 5, USD 8.
