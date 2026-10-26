# Actual versus forecast: how variance is explained

Code: `src/cashpilot/engine/compare.py`. Output: `forecast_vs_actual` (per run, scenario,
entity and horizon week) and `variance_attribution` (the item-level drill-down, base scenario).

## What is compared

* Weeks are horizon weeks (`week_no` 1-13, starting on the cutoff date). Only weeks that have
  fully elapsed by the end of the actuals period are compared.
* **Forecast (F)**: the run's projected net external cash flow for the entity and week, in USD at
  the run's rate (`r_c`, including any scenario FX shock).
* **Actual (A)**: booked external cash flow in the same week, each posting valued at the rate of its
  own day (`r_p`). Internal transfers, pool sweeps, FX conversions between pool accounts and
  restricted accounts are excluded on both sides.

## Parts and links

Actual cash is cut into **parts**: one per settlement allocation for invoices and bills (a bulk
payment becomes several parts), otherwise one per posting. A part is linked to the forecast item
it realises: invoice/bill → its subledger forecast item; payroll, rent, tax, debt and manual
items → `ledger_entry.cf_id`. Small operating flows are matched to run-rate items in aggregate.

## The decomposition

For a forecast item *i* expected in week *w_f* with forecast value `F_i`, and its parts *p* in weeks
*w_p* with `T_p` = part at `r_c` and `A_p` = part at `r_p`:

| Situation | Driver | Amount | Week |
|---|---|---|---|
| item realised (≥ 1 part in the window) | TIMING (only for parts with `w_p ≠ w_f`) | `+T_p` and `−T_p` | `w_p` and `w_f` |
| | AMOUNT | `Σ T_p − F_i` | `w_f` |
| | FX | `A_p − T_p` | `w_p` |
| item not realised in the window | NOT_REALIZED (TIMING if paid after the window) | `−F_i` | `w_f` |
| item flagged by a data-quality rule (duplicate, mixed currency) | DATA_QUALITY | `−F_i`, `+A_p` | `w_f`, `w_p` |
| run-rate item | RUN_RATE | `−F_i` | `w_f` |
| small operating flows | RUN_RATE | `+A_p` (summed per entity-week) | `w_p` |
| part of an item recorded after the cutoff | NEW_AFTER_CUTOFF | `+A_p` | `w_p` |
| part of an item known but forecast outside the window | TIMING | `+A_p` | `w_p` |
| part with no forecast item (fees, interest) | UNFORECASTED | `+A_p` | `w_p` |

Per week, the terms for a realised item sum to `A_p` in each actual week and `−F_i` in the
forecast week, so summed over all items and parts:

    Σ drivers = Σ A − Σ F = variance        residual = 0 by construction

All amounts are integer USD cents, so the identity is exact. The validator checks it for every
row (`A-VAR-explained`) and checks that the item-level drill-down adds up to each driver
(`A-VAR-drilldown`).

## Reading it

`cashpilot explain --data data/starter --run <run> --entity <entity> --week <n>` prints the
forecast, actual, variance and the top records behind each driver. The evaluation report gives
the share of absolute variance per driver across all approved versions: most of it is business
invoiced after the cutoff and customers paying in a different week than their due date - the two
levers the delayed-receipt scenario stresses.
