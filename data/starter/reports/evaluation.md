# Evaluation — `starter` dataset (seed 20261022)

## Detection quality against the ground truth

Detectors run without the ground truth; labels are joined afterwards to score them.

| Edge case | Labelled | Detected | Precision | Recall | F1 | Decision accuracy |
|---|---|---|---|---|---|---|
| BALANCE_BREAK | 6 | 6 | 100.0% | 100.0% | 100.0% | 100.0% |
| DUPLICATE_CASH_FLOW | 10 | 10 | 100.0% | 100.0% | 100.0% | 100.0% |
| FX_RATE_MISSING | 12 | 12 | 100.0% | 100.0% | 100.0% | 100.0% |
| LOOKAHEAD_LEAKAGE | 1 | 1 | 100.0% | 100.0% | 100.0% | 100.0% |
| MIXED_CURRENCY | 6 | 6 | 100.0% | 100.0% | 100.0% | 100.0% |

Recall by variant:

| Edge case | Variant | Labelled | Detected | Recall |
|---|---|---|---|---|
| BALANCE_BREAK | BANK_ONLY_CHARGE | 4 | 4 | 100.0% |
| BALANCE_BREAK | PAYMENT_REJECTED_BY_BANK | 2 | 2 | 100.0% |
| DUPLICATE_CASH_FLOW | EXACT_REFERENCE | 7 | 7 | 100.0% |
| DUPLICATE_CASH_FLOW | FUZZY_MATCH | 3 | 3 | 100.0% |
| FX_RATE_MISSING | LONG_GAP | 5 | 5 | 100.0% |
| FX_RATE_MISSING | SHORT_GAP | 7 | 7 | 100.0% |
| LOOKAHEAD_LEAKAGE | LATEST_SNAPSHOT_USED | 1 | 1 | 100.0% |
| MIXED_CURRENCY | ITEM_CURRENCY_MISMATCH | 3 | 3 | 100.0% |
| MIXED_CURRENCY | UNCONVERTED_AMOUNT | 3 | 3 | 100.0% |

Negative controls (legitimate look-alikes): 9, flagged: **0**.

`FUZZY_BEYOND_TOLERANCE` duplicates are re-keyed 5-6 days away from the original, outside the documented 3-day matching tolerance; they are included on purpose to show where the rule stops working.

## Forecast accuracy (approved versions, base scenario)

Weekly **net external cash flow** per entity, compared with actuals for every fully elapsed horizon week. WAPE = Σ|actual − forecast| / Σ|actual|; bias = Σ(actual − forecast) / Σ|actual|.

| Horizon | WAPE | Bias | Entity-weeks |
|---|---|---|---|
| week 1 | 49.2% | 3.0% | 93 |
| weeks 2-4 | 83.2% | -38.1% | 259 |
| weeks 5-13 | 82.4% | -21.6% | 647 |

By scenario (same versions):

| Scenario | Week 1 WAPE | Weeks 2-4 WAPE | Weeks 5-13 WAPE |
|---|---|---|---|
| BASE | 49.2% | 83.2% | 82.4% |
| DELAY | 65.6% | 60.7% | 78.8% |
| STRESS | 92.0% | 74.0% | 78.1% |

**Look-ahead signature.** Week-1 WAPE of the leaky legacy runs: 166.9%; of their as-of re-runs: 106.1%; of all other approved runs: 45.5%. The leaky runs started from a balance seven days old *and* dropped items already settled, so their first week is distorted; lineage, not accuracy, is what proves the leak (rule R-LEAK-001).

## Cash balance accuracy (group level)

Projected group available cash at each forecast week-end vs actual group available cash (internal pooling nets out at group level; restricted cash excluded on both sides).

| Horizon | MAPE | Bias | Observations |
|---|---|---|---|
| week 1 | 1.8% | -0.2% | 20 |
| weeks 2-4 | 5.4% | 5.3% | 56 |
| weeks 5-13 | 12.8% | 12.6% | 142 |

## What explains the variance

Share of absolute variance by driver (approved versions, base scenario). Drivers add up exactly to actual − forecast; total unexplained residual: **USD 0**.

| Driver | Share of absolute variance | Net effect (USD) |
|---|---|---|
| timing | 35.4% | -5,927,505 |
| amount | 1.2% | -944,300 |
| fx | 0.6% | 301,678 |
| new_after_cutoff | 43.9% | -125,135,369 |
| unforecasted | 0.1% | 1,039,751 |
| not_realized | 8.3% | -40,053,864 |
| run_rate | 7.5% | 474,214 |
| data_quality | 2.9% | -79,183 |

Most variance comes from business that did not exist at the cutoff (invoices raised later and paid within the horizon) and from customers paying on a different week than their due date - exactly the levers the delayed-receipt scenario stresses.

## Reconciliation

4,367 bank statement days; 99.9% reconcile to the ledger exactly. 6 breaks raised (3 above materiality). After a break the bank and book balances stay apart until the item is booked: 391 account-days across 5 accounts carry an open difference (visible in `daily_cash_position.bank_minus_book`).
