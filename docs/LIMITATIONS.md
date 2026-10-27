# Limitations and known gaps

Stated plainly so that reviewers can judge what the numbers mean.

## Forecasting

* **Known items plus run-rate only.** The forecast projects invoices, bills, schedules, manual
  submissions and a run-rate for small flows. It does not forecast *new* invoices that will be
  raised after the cutoff, so weekly net-flow accuracy degrades with the horizon (WAPE ~64% in
  week 1 rising to ~94% by weeks 5-13 at full scale) and "new business after the cutoff" is the
  largest variance driver (~50%). Group cash-balance accuracy is much better (~1.6% MAPE in week 1,
  ~6.6% by weeks 5-13) because new inflows and outflows largely offset. A sales/purchase pipeline
  model would be the next step; the variance attribution already isolates the gap.
* **Entity positions are standalone.** Forecast entity cash ignores future pool sweeps (a treasury
  decision, not a cash flow). Entity breaches are therefore "before pooling"; the group view is the
  consolidated picture.
* **Rule-based, not learned.** Overdue roll-forward days and scenario parameters are documented
  judgement, not fitted to data. This was a deliberate choice for traceability (D-009).
* **No hedging, credit facilities or intraday positions.** Overdraft limits exist on accounts but
  committed facilities are not part of available liquidity.

## Data generation

* **Simplified calendar**: weekends plus 1 January and 25 December for every country.
* **Value date = posting date** for every posting; there is no float between book and bank except
  the injected anomalies.
* **One rate per business day** (closing). No bid/ask spread on conversions.
* **Cross-currency receivables** are only USD invoices collected into a non-USD account (single
  rate). Partial and bulk payments are same-currency only.
* **Behavioural parameters** (delay distributions, hold and deferral rates, fees, interest) are
  plausible but not calibrated to any real portfolio.

## Detection

* **Duplicate matching tolerance is 3 days.** Re-keyed items dated further away are missed by
  design (recall 87% at full scale, see `reports/evaluation.md`); widening the tolerance trades
  this against false positives on legitimate recurring flows.
* **Deterministic rules score 100%** on their own edge cases because the edge cases are well
  defined. That is evidence the rules are implemented correctly, not that they would be perfect on
  messier real data; the negative controls and the deliberately hard duplicates are there to keep
  the evaluation honest.

## Engineering

* **Single-user, file-based.** Workflow commands rewrite CSV tables; there is no concurrency
  control or real authentication (actors are named with `--as-user`).
* **Reproducibility scope.** Checksums are guaranteed identical with the pinned library versions
  (`requirements.txt`). Floating-point maths is limited to FX conversions (IEEE-754
  multiplication, deterministic on every platform) and seeded random draws; CI compares the
  starter checksums on Ubuntu and Windows.
* **Size.** The full bundle (CSV + JSON + SQL) is ~0.6 GB, so only its manifest, ground truth,
  validation summary and reports are committed; the bulk files are regenerated with one command.

## Currency and consolidation

* **Entity totals on a missing-rate day are understated, by design, and flagged.** If a balance cannot be converted
  (more than 3 missing fixings) its USD value stays empty and the entity total holds only what could be converted,
  with `fx_status = INCOMPLETE`. Totals are not estimated. Evaluation metrics skip such days
  (`excluded_incomplete_fx`) and the dashboard marks them. In the committed data no comparison was affected.
* **One reporting currency per dataset (USD).** Engine columns embed `usd` and amounts are held per currency in minor
  units; making the reporting currency configurable would change the schema, so it was not attempted.
* **The FX shock** in the stress scenario is a uniform percentage on every non-reporting currency applied to balances
  and flows alike; it is not a currency-by-currency view.

## Dashboard

* Read-only by design (see [DASHBOARD.md](DASHBOARD.md)); actions live in the CLI where permissions, four-eyes and audit exist.
* No authentication: a local review tool for synthetic data, not for exposure to a network.
* Item-level variance drill-down exists for the base scenario only.
* Long lists (ledger entries, invoices, bills) show the first 1,000-2,000 rows; the download has all of them.
* The screenshots were captured from the running app on one machine; widget layout may differ slightly between
  Streamlit versions (1.66.1 is pinned).
