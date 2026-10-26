# Rule catalogue

Every rule has an ID. Generation rules explain how outcomes arise (never random labels);
engine rules are decisions CashPilot applies; detection rules raise exceptions; injection rules
create labelled edge cases. Source: `src/cashpilot/generate/`, `engine/`, `quality/`.

## Generation rules (how the synthetic world behaves)

| ID | Rule |
|---|---|
| G-AR-01 | Customer payment delay is drawn from a distribution chosen by the customer's risk tier: A ≈ on time (normal, σ 2 days, clipped −5..+7), B gamma(2, 4), C gamma(2, 10), D gamma(2, 22) days after the due date; payment rolls to the next business day. |
| G-AR-02 | Never-pay probability by tier: C 3%, D 12%. Unpaid invoices become OVERDUE 30 days after due (policy `overdue_grace_days`) and are WRITTEN_OFF on the first business day of the month after due + 90 days. |
| G-AR-03 | Partial payments (A 2%, B 4%, C 8%, D 10%): 40-70% first, the rest 10-40 days later. |
| G-AR-04 | Bulk payments: same customer, entity, account and currency, same ISO week: 30% are paid with one transfer on the latest date (N:M settlement). |
| G-AR-05 | Customers warn of late payment in advance (A 30%, B 50%, C 60%, D 40% of invoices ≥ 7 days late) → a DATE_CHANGE revision 3-15 days before payment; 30% of tier-D never-payers make a broken promise. |
| G-AR-06 | A quarter of invoices go to foreign customers; USD invoices to entities without a USD account are converted into the functional currency (legitimate cross-currency items). |
| G-AP-01 | Bills are paid on the last business day on or before the due date. |
| G-AP-02 | 15% of bills from tier C/D suppliers go ON_HOLD two days after the bill; 80% are released after 10-30 days and paid, 20% are cancelled. |
| G-AP-03 | Treasury defers 4% of other payments by 7-14 days (DATE_CHANGE recorded 2-5 days before). |
| G-AP-04 | Bills ≥ USD 250,000 (policy `approval_threshold_usd`) and all one-offs need a risk reviewer's approval; others are auto-approved. |
| G-ONE-01 | 24 large one-off payments (capex, tax, debt, legal, the April acquisition) of 0.5-1.5 months of the entity's outflows; 70% known 30-90 days ahead, 30% only 2-10 days ahead. |
| G-SCH-01 | Payroll on the 25th (±1.5% actual vs plan), rent on the 1st, quarterly tax on the 15th (±8%), debt service on the 28th for large entities. |
| G-POOL-01 | Weekly (Friday) sweeps bring operating, collection and payroll accounts to target balances against the currency's pool header. |
| G-POOL-02 | Payroll, tax and one-off payments are pre-funded from the pool header on the morning of payment; new deposit accounts get an initial placement. |
| G-POOL-03 | Overdraft protection: an account (or non-USD header) below its overdraft limit at end of day is topped back to target (headers via FX from the USD header). |
| G-POOL-04 | Non-USD pool headers are rebalanced into USD on the first business day of each month; deposit accounts earn monthly interest on their average balance. |
| G-RR-01 | Run-rate items estimate weekly small operating flows from the annual budget; each month the next 13 weeks are re-estimated from the last 28 days of actuals (AMOUNT_CHANGE revisions). |
| G-LED-01 | The ledger holds exactly the configured number of entries; small operating flows fill the remainder (fixed-point iteration, see D-016). |

## Engine rules (decisions CashPilot applies)

| ID | Rule |
|---|---|
| F-ASOF-001 | A forecast run sees only records *recorded* before its knowledge cutoff (08:00 UTC on the cutoff date): items, revisions, statements and FX rates. |
| F-ROLL-001 | Overdue receivables are expected cutoff + 3 / 7 / 14 / 30 days for tiers A / B / C / D. |
| F-ROLL-002 | Overdue payables are expected cutoff + 3 days. |
| F-ROLL-003 | Overdue payroll, rent, tax and debt service are due on the cutoff date. |
| F-ROLL-004 | Manual items more than 7 days past their date are dropped (`EXCLUDED_STALE`); others +3 days. |
| F-DQ-001 | CashPilot runs exclude manual items that duplicate a subledger item (`EXCLUDED_DUPLICATE`). |
| F-DQ-002 | CashPilot runs convert mixed-currency items at the snapshot rate (`CONVERTED`), or quarantine them if no rate is available. |
| F-LIQ-001 | Available cash excludes restricted accounts; a breach is projected available cash below the entity's `min_liquidity_buffer` (converted at the same rate). |
| R-FX-001 (staleness) | A missing fixing may be replaced by the previous one while ≤ 3 expected fixings are missing (`FALLBACK`); beyond that the value is `MISSING` / conversion blocked. |
| W-001 | Four-eyes: the approver of a run must differ from its preparer and submitter. |
| W-002 | A run cannot be approved with an open CRITICAL exception or a HIGH exception that is neither resolved nor waived. |
| W-003 | Waivers require a risk reviewer and a written justification. |
| W-004 | Account holders may view only their own entity; every attempted action is audited (ALLOWED/DENIED). |
| W-005 | Leaky runs are never edited: an as-of re-run is approved and the old version receives a SUPERSEDED event. |

## Detection rules (exceptions)

| ID | Detects | Severity | Decision |
|---|---|---|---|
| R-RECON-001 | Bank movement ≠ booked ledger movement on an account-day (opening + ledger ≠ closing) | HIGH if ≥ USD 1,000 (policy), else LOW | `RAISE_RECON_BREAK` |
| R-FX-001 | Business-day fixing missing | MEDIUM within tolerance, HIGH beyond | `USE_PREVIOUS_RATE` / `BLOCK_CONVERSION` |
| R-DUP-001 | Manual item with the same invoice/bill reference as a subledger item | MEDIUM | `EXCLUDE_DUPLICATE` |
| R-DUP-002 | Manual item with same entity, account, direction, currency, counterparty and amount, dated ≤ 3 days apart | MEDIUM | `EXCLUDE_DUPLICATE` |
| R-CUR-001 | Item currency ≠ account currency, no conversion recorded | HIGH | `CONVERT_AT_CUTOFF_RATE` |
| R-CUR-002 | Item linked to a foreign-currency document carries the document's amount unconverted | HIGH | `CONVERT_AT_CUTOFF_RATE` |
| R-LEAK-001 | A run's lineage contains items, statements or rates recorded after its knowledge cutoff | CRITICAL | `SUPERSEDE_WITH_RERUN` |
| R-LIQ-001 | Business alert: projected available cash below buffer (base HIGH, delayed MEDIUM, stress LOW) | as stated | `FUNDING_REVIEW` |

## Exception playbook (who does what)

| Exception | Steps |
|---|---|
| BALANCE_BREAK LOW | analyst RESOLVES (item booked / payment status confirmed) |
| BALANCE_BREAK HIGH | analyst ESCALATES → reviewer RESOLVES (adjustment approved) |
| FX_RATE_MISSING MEDIUM | analyst RESOLVES (previous fixing within tolerance) |
| FX_RATE_MISSING HIGH | analyst ESCALATES → reviewer WAIVES with justification |
| DUPLICATE_CASH_FLOW | analyst RESOLVES (excluded by the gate, account holder notified) |
| MIXED_CURRENCY | analyst ESCALATES → reviewer RESOLVES (converted by the gate, source fix requested) |
| LOOKAHEAD_LEAKAGE | analyst ESCALATES → analyst prepares an as-of re-run → reviewer approves it → old run SUPERSEDED → reviewer RESOLVES |
| LIQUIDITY_BREACH | HIGH: escalated, reviewer agrees a funding plan; MEDIUM/LOW: analyst monitors |

## Injection rules (labelled edge cases)

| ID | Edge case | What changes |
|---|---|---|
| INJ-REC-01 | Opening + ledger ≠ closing | The bank debits a charge the ledger never booked (statement only) |
| INJ-REC-02 | Opening + ledger ≠ closing | A booked payment is rejected by the bank (statement only) |
| INJ-FX-01 / 02 | FX rate missing | 1-3 / 5 consecutive business-day fixings deleted (never ones referenced by a conversion) |
| INJ-DUP-01 / 02 / 03 | Cash flow counted twice | Account holder re-keys a subledger item: same reference / own reference within 3 days / 5-6 days away |
| INJ-CUR-01 / 02 | Currency mixed without conversion | A converted item reverts to the invoice currency / carries the invoice's foreign amount |
| INJ-LEAK-01 | Forecast uses actual after cutoff | A legacy weekly run re-generated a week late from the latest data while claiming the original cutoff |
| NEG-* | Negative controls | Legitimate look-alikes labelled `NO_ISSUE` (converted items, manual items, weekend dates, large booked movements, the run next to a leaky one) |
