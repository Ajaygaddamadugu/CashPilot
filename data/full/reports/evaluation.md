# Evaluation — `full` dataset (seed 20261022)

## Detection quality against the ground truth

Detectors run without the ground truth; labels are joined afterwards to score them.

| Edge case | Labelled | Detected | Precision | Recall | F1 | Decision accuracy |
|---|---|---|---|---|---|---|
| BALANCE_BREAK | 40 | 40 | 100.0% | 100.0% | 100.0% | 100.0% |
| DUPLICATE_CASH_FLOW | 60 | 52 | 100.0% | 86.7% | 92.9% | 100.0% |
| FX_RATE_MISSING | 23 | 23 | 100.0% | 100.0% | 100.0% | 100.0% |
| LOOKAHEAD_LEAKAGE | 3 | 3 | 100.0% | 100.0% | 100.0% | 100.0% |
| MIXED_CURRENCY | 40 | 40 | 100.0% | 100.0% | 100.0% | 100.0% |

Recall by variant:

| Edge case | Variant | Labelled | Detected | Recall |
|---|---|---|---|---|
| BALANCE_BREAK | BANK_ONLY_CHARGE | 29 | 29 | 100.0% |
| BALANCE_BREAK | PAYMENT_REJECTED_BY_BANK | 11 | 11 | 100.0% |
| DUPLICATE_CASH_FLOW | EXACT_REFERENCE | 30 | 30 | 100.0% |
| DUPLICATE_CASH_FLOW | FUZZY_BEYOND_TOLERANCE | 8 | 0 | 0.0% |
| DUPLICATE_CASH_FLOW | FUZZY_MATCH | 22 | 22 | 100.0% |
| FX_RATE_MISSING | LONG_GAP | 5 | 5 | 100.0% |
| FX_RATE_MISSING | SHORT_GAP | 18 | 18 | 100.0% |
| LOOKAHEAD_LEAKAGE | LATEST_SNAPSHOT_USED | 3 | 3 | 100.0% |
| MIXED_CURRENCY | ITEM_CURRENCY_MISMATCH | 20 | 20 | 100.0% |
| MIXED_CURRENCY | UNCONVERTED_AMOUNT | 20 | 20 | 100.0% |

Negative controls (legitimate look-alikes): 35, flagged: **0**.

`FUZZY_BEYOND_TOLERANCE` duplicates are re-keyed 5-6 days away from the original, outside the documented 3-day matching tolerance; they are included on purpose to show where the rule stops working.

## Forecast accuracy (approved versions, base scenario)

Weekly **net external cash flow** per entity, compared with actuals for every fully elapsed horizon week. WAPE = Σ|actual − forecast| / Σ|actual|; bias = Σ(actual − forecast) / Σ|actual|.

| Horizon | WAPE | Bias | Entity-weeks |
|---|---|---|---|
| week 1 | 63.6% | 2.0% | 1,157 |
| weeks 2-4 | 87.2% | -20.5% | 3,291 |
| weeks 5-13 | 93.5% | 13.6% | 8,253 |

By scenario (same versions):

| Scenario | Week 1 WAPE | Weeks 2-4 WAPE | Weeks 5-13 WAPE |
|---|---|---|---|
| BASE | 63.6% | 87.2% | 93.5% |
| DELAY | 72.2% | 80.1% | 92.2% |
| STRESS | 99.7% | 93.9% | 95.1% |

**Look-ahead signature.** Week-1 WAPE of the leaky legacy runs: 124.2%; of their as-of re-runs: 68.9%; of all other approved runs: 62.9%. The leaky runs started from a balance seven days old *and* dropped items already settled, so their first week is distorted; lineage, not accuracy, is what proves the leak (rule R-LEAK-001).

## Cash balance accuracy (group level)

Projected group available cash at each forecast week-end vs actual group available cash (internal pooling nets out at group level; restricted cash excluded on both sides).

| Horizon | MAPE | Bias | Observations |
|---|---|---|---|
| week 1 | 1.6% | -0.0% | 39 |
| weeks 2-4 | 3.1% | 2.5% | 111 |
| weeks 5-13 | 6.6% | 1.2% | 279 |

## What explains the variance

Share of absolute variance by driver (approved versions, base scenario). Drivers add up exactly to actual − forecast; total unexplained residual: **USD 0**.

| Driver | Share of absolute variance | Net effect (USD) |
|---|---|---|
| timing | 32.9% | -146,447,555 |
| amount | 1.4% | 49,728,135 |
| fx | 0.9% | 39,364,779 |
| new_after_cutoff | 49.9% | 824,611,664 |
| unforecasted | 0.6% | 116,289,173 |
| not_realized | 8.6% | -210,848,495 |
| run_rate | 4.6% | -14,144,534 |
| data_quality | 1.1% | -10,268,744 |

Most variance comes from business that did not exist at the cutoff (invoices raised later and paid within the horizon) and from customers paying on a different week than their due date - exactly the levers the delayed-receipt scenario stresses.

## Reconciliation

28,603 bank statement days; 99.9% reconcile to the ledger exactly. 40 breaks raised (18 above materiality). After a break the bank and book balances stay apart until the item is booked: 3,060 account-days across 35 accounts carry an open difference (visible in `daily_cash_position.bank_minus_book`).
