# Data profile — `full` dataset

## Row counts

| Table | Rows |
|---|---|
| `currency` | 5 |
| `app_user` | 37 |
| `counterparty` | 1,000 |
| `currency_rate` | 961 |
| `liquidity_scenario` | 4 |
| `scenario_assumption` | 10 |
| `scenario_assumption_link` | 22 |
| `legal_entity` | 30 |
| `bank_account` | 150 |
| `receivable` | 8,628 |
| `payable` | 7,059 |
| `cash_flow_forecast` | 20,000 |
| `ledger_entry` | 100,000 |
| `settlement_allocation` | 13,591 |
| `bank_statement` | 28,603 |
| `bank_account_event` | 154 |
| `receivable_event` | 16,768 |
| `payable_event` | 20,431 |
| `cf_revision` | 22,443 |
| `forecast_run` | 46 |
| `forecast_run_scenario` | 135 |
| `forecast_run_item` | 155,521 |
| `forecast_run_balance_input` | 6,753 |
| `forecast_run_fx_input` | 184 |
| `forecast_position` | 364,819 |
| `scenario_assumption_effect` | 571 |
| `forecast_run_event` | 187 |
| `daily_cash_position` | 40,031 |
| `entity_cash_position` | 8,100 |
| `exception` | 195 |
| `exception_event` | 659 |
| `audit_event` | 680 |
| `forecast_vs_actual` | 43,147 |
| `variance_attribution` | 303,378 |

## Customer payment behaviour by risk tier (rule-driven)

| Tier | Invoices | Paid | Median days late | Paid > 7 days late | Written off |
|---|---|---|---|---|---|
| A | 3,447 | 3,026 | 1.0 | 2.1% | 0 |
| B | 3,318 | 2,783 | 8.0 | 51.1% | 0 |
| C | 1,251 | 942 | 19.0 | 84.9% | 24 |
| D | 612 | 336 | 35.0 | 95.8% | 39 |

## FX movement

| Currency | Realised annual volatility | Configured | Change over the period |
|---|---|---|---|
| EUR/USD | 7.3% | 7.0% | -5.6% |
| GBP/USD | 9.2% | 8.0% | -3.1% |
| INR/USD | 4.0% | 4.0% | -3.4% |
| JPY/USD | 10.1% | 10.0% | -14.1% |

## Ledger

| Entry type | Count |
|---|---|
| OPERATING_RECEIPT | 42,680 |
| OPERATING_PAYMENT | 34,920 |
| AR_RECEIPT | 7,043 |
| AP_PAYMENT | 6,222 |
| POOL_SWEEP | 5,956 |
| BANK_FEE | 1,318 |
| POOL_FUNDING | 786 |
| RENT | 267 |
| PAYROLL | 267 |
| INTEREST | 165 |
| OTHER_RECEIPT | 125 |
| TAX | 89 |
| FX_CONVERSION | 72 |
| OTHER_PAYMENT | 68 |
| DEBT_SERVICE | 18 |
| ACCOUNT_CLOSURE | 4 |

Absolute posting amounts by currency (major units):

| Currency | p10 | p50 | p90 | p99 |
|---|---|---|---|---|
| EUR | 1,434 | 6,585 | 140,359 | 1,198,234 |
| GBP | 1,348 | 5,057 | 50,044 | 1,104,395 |
| INR | 138,654 | 589,187 | 11,839,846 | 116,606,815 |
| JPY | 255,863 | 984,615 | 11,337,772 | 358,231,308 |
| USD | 1,600 | 8,922 | 226,925 | 1,345,510 |

Postings by weekday: Monday 20,222, Tuesday 16,549, Wednesday 17,148, Thursday 16,757, Friday 29,324.

Large one-off payments: 24 (CAPEX 9, TAX_SETTLEMENT 7, DEBT_REPAYMENT 6, ACQUISITION 1, LEGAL_SETTLEMENT 1).

Entities by size tier: L 3, M 15, S 12. Accounts by currency: EUR 41, GBP 21, INR 23, JPY 13, USD 52.
