"""Plain-language wording for the dashboard: labels, explanations and the glossary.

Everything a user reads that is not a number lives here, so it can be reviewed in one place and tested for
completeness (every code the engine can produce has an explanation).
"""

from __future__ import annotations

# What each variance driver means (engine/compare.py)
DRIVER_TEXT = {
    "TIMING": "The cash arrived in a different week than forecast (earlier or later).",
    "AMOUNT": "The cash arrived for a different amount than forecast (for example a part payment).",
    "FX": "Exchange rates moved between the forecast and the day the cash arrived.",
    "NEW_AFTER_CUTOFF": "Business that did not exist when the forecast was made (invoices raised afterwards).",
    "UNFORECASTED": "Cash that was never forecast, such as bank fees and interest.",
    "NOT_REALIZED": "Forecast items that did not happen within the window.",
    "RUN_RATE": "Small day-to-day flows that are estimated from a weekly average instead of item by item.",
    "DATA_QUALITY": "Items removed or converted because of a data-quality rule (duplicates, mixed currency).",
}
DRIVER_LABEL = {
    "TIMING": "Timing", "AMOUNT": "Amount", "FX": "FX rates", "NEW_AFTER_CUTOFF": "New business after the forecast",
    "UNFORECASTED": "Never forecast (fees, interest)", "NOT_REALIZED": "Did not happen", "RUN_RATE": "Small daily flows (run-rate)",
    "DATA_QUALITY": "Data-quality rules",
}

# How a forecast item was treated in a run (forecast_run_item.treatment)
TREATMENT_TEXT = {
    "INCLUDED": "Used as recorded",
    "OVERDUE_ROLLED": "Overdue, so moved to a later date by the roll-forward rule",
    "EXCLUDED_STALE": "Dropped: a manual item too far past its date",
    "EXCLUDED_DUPLICATE": "Dropped: it duplicates another item (counting it would double the cash flow)",
    "CONVERTED": "Currency converted by the data-quality gate",
    "QUARANTINED": "Set aside: it could not be converted",
}

# Why a forecast item changed between two runs (revision reasons and run-diff categories)
REASON_TEXT = {
    "REALIZED": "It happened: the cash was booked",
    "PAID_IN_FULL": "Paid in full",
    "WRITTEN_OFF": "Written off as uncollectable",
    "NOT_REALIZED": "Did not happen and was closed",
    "PAYMENT_CANCELLED": "The payment was cancelled",
    "CUSTOMER_ADVISED_DELAY": "The customer warned that they will pay late",
    "PARTIAL_PAYMENT": "Only part of it has been paid so far",
    "SUPPLIER_HOLD": "The supplier payment was put on hold",
    "HOLD_RELEASED": "The hold was released and a new date set",
    "PAYMENT_DEFERRED": "Treasury deferred the payment",
    "RUN_RATE_REESTIMATE": "The run-rate estimate was refreshed from recent actuals",
}
RUN_DIFF_TEXT = {
    "NEW_AFTER_PREVIOUS_CUTOFF": "It became known after the earlier run was made",
    "ENTERED_THE_HORIZON": "Its date moved into the 13-week window",
    "OVERDUE_ROLLED": "It is overdue, so the roll-forward rule moved it",
    "RATE_OR_ROLL_RULE": "An FX rate or the roll-forward rule changed its value",
    "LEFT_THE_SNAPSHOT_OR_HORIZON": "It left the 13-week window",
}
DROP_TEXT = {"EXCLUDED_DUPLICATE": "it duplicates another item", "EXCLUDED_STALE": "a manual item too far past its date",
             "QUARANTINED": "it could not be converted"}
CHANGE_PARTS = {"TREATMENT": "how it is handled", "DATE": "date", "AMOUNT_OR_FX": "amount or FX rate"}


def plain_reason(code: str) -> str:
    """Explain a run-diff reason such as ``SETTLED: REALIZED`` or ``NEW_AFTER_PREVIOUS_CUTOFF``."""
    if code in RUN_DIFF_TEXT:
        return RUN_DIFF_TEXT[code]
    if ": " in code:
        kind, detail = code.split(": ", 1)
        if kind == "EXCLUDED_BY_RULE":
            return f"Dropped by a data-quality rule ({DROP_TEXT.get(detail, detail.lower())})"
        if detail in REASON_TEXT:
            return REASON_TEXT[detail]
    return f"Other: {code}"


def plain_change(kind: str) -> str:
    if kind == "ADDED":
        return "New in this run"
    if kind == "REMOVED":
        return "No longer in this run"
    parts = [CHANGE_PARTS.get(p, p) for p in kind.removeprefix("CHANGED_").split("+")]
    return "Changed: " + (", ".join(parts[:-1]) + " and " + parts[-1] if len(parts) > 1 else parts[0])


# The five edge cases of the brief, in plain words
EDGE_CASES = {
    "BALANCE_BREAK": ("Opening balance + ledger does not equal the bank's closing balance",
                      "The bank statement shows a different movement than the ledger booked (a fee the ledger missed, or a payment the bank rejected).",
                      "Exceptions"),
    "FX_RATE_MISSING": ("FX rate missing",
                        "A business day has no exchange-rate fixing. Up to 3 missing days the previous rate is used and flagged; beyond that conversion is blocked.",
                        "Accounts & currencies, Exceptions"),
    "DUPLICATE_CASH_FLOW": ("Cash flow counted twice",
                            "A manual forecast item repeats an invoice or bill that is already forecast from the ledger system.",
                            "Exceptions, Audit & exports"),
    "LOOKAHEAD_LEAKAGE": ("Forecast uses actual data after its cutoff",
                          "A forecast version was built with records that were only recorded after the date it claims to be as of.",
                          "Exceptions, Audit & exports"),
    "MIXED_CURRENCY": ("Currency mixed without conversion",
                       "A forecast item is in a different currency from its bank account (or carries an invoice's foreign amount) with no conversion.",
                       "Exceptions"),
}

ROLE_TEXT = {
    "ACCOUNT_HOLDER": "Account holder (customer)",
    "OPS_ANALYST": "Operations analyst",
    "RISK_REVIEWER": "Risk / compliance reviewer",
    "SYS_ADMIN": "System administrator",
    "SYSTEM": "System (scheduler)",
}
ACTION_TEXT = {
    "VIEW_ENTITY": "view an entity's cash (account holders: only their own)",
    "CREATE_RUN": "create a forecast run",
    "SUBMIT_RUN": "submit a forecast run for approval",
    "APPROVE_RUN": "approve a forecast run (never their own)",
    "REJECT_RUN": "reject a forecast run",
    "SUPERSEDE_RUN": "replace a forecast version with a corrected one",
    "ASSIGN_EXCEPTION": "assign an exception",
    "ESCALATE_EXCEPTION": "escalate an exception",
    "RESOLVE_EXCEPTION": "resolve an exception",
    "WAIVE_EXCEPTION": "waive an exception, with a written reason",
}
ROLE_EXTRA = {
    "ACCOUNT_HOLDER": "Submits manual forecast items for their own entity.",
    "SYS_ADMIN": "Opens and closes accounts and publishes scenario versions (recorded as events).",
    "RISK_REVIEWER": "Can freeze accounts and approves large payments.",
    "OPS_ANALYST": "Runs reconciliation and forecasts and works through exceptions.",
    "SYSTEM": "Runs scheduled feeds and raises exceptions automatically.",
}

GLOSSARY = {
    "Available vs restricted cash": "Restricted accounts (for example escrow) cannot be used, so available cash = total cash minus restricted cash.",
    "Minimum buffer / headroom": "Each entity must keep a minimum amount of available cash (its buffer). Headroom = available cash minus that buffer; negative headroom means a shortfall.",
    "Forecast run / version": "One 13-week projection made as of a cutoff date. Corrections create a new version; old versions stay, marked as replaced.",
    "Cutoff / knowledge cutoff": "The moment a run is 'as of': it may only use records that were recorded before it.",
    "Scenario": "A set of documented assumptions applied to the same data: Base (none), Delayed receipt (customers pay later) and Stress (delays, haircuts, earlier supplier payments, weaker USD value).",
    "FX status: OK / FALLBACK / MISSING": "OK = the day's rate was available. FALLBACK = the previous rate was used (up to 3 business days old). MISSING = no usable rate, so the value is left empty.",
    "INCOMPLETE": "An entity total on a day when at least one of its balances could not be converted. The total then leaves that balance out; it is flagged, never estimated.",
    "Lineage / treatment": "The record of exactly which items a run used and how each was handled (used, moved, dropped, converted).",
    "Reproducible": "Re-running a version from the data known at its cutoff gives byte-identical results (checked with hashes).",
    "WAPE": "Typical size of the weekly error as a share of the real cash flow (lower is better). It looks large for net weekly flows because they are small differences of big numbers.",
    "MAPE": "Typical error of the projected group cash balance as a share of the real balance (lower is better).",
    "Bias": "Whether forecasts lean one way: positive means actual cash ended higher than forecast.",
    "Ground truth": "The answer key of deliberately injected problems. It is kept apart from the data and used only to score the detectors.",
}

# Friendly column labels, with a short help text where the meaning is not obvious
LABELS = {
    "entity_id": "Entity ID", "entity_name": "Entity", "account_id": "Account", "currency": "Currency", "size_tier": "Size",
    "total_usd": "Total cash (USD)", "available_usd": "Available cash (USD)", "restricted_usd": "Restricted cash (USD)",
    "min_buffer_usd": "Minimum buffer (USD)", "headroom_usd": "Headroom (USD)", "fx_status": "FX status",
    "accounts_active": "Active accounts", "buffer_status": "Buffer status", "bank_name": "Bank", "account_type": "Account type",
    "restricted": "Restricted?", "local_balance": "Balance (account currency)", "fx_rate_id": "Rate used", "rate_usd_per_unit": "USD per 1 unit",
    "rate_date": "Rate date", "balance_usd": "Balance (USD)", "bank_minus_book_local": "Bank minus book (account currency)",
    "accounts": "Accounts", "local_total": "Total (account currency)", "usd_value": "Value (USD)",
    "accounts_without_rate": "Accounts without a rate", "rate": "USD per 1 unit", "worst_fx_status": "Worst FX status",
    "share_of_total": "Share of total", "usd_impact_of_move": "Effect of the FX move (USD)",
    "week_no": "Week", "week_start": "Week starts", "week_end": "Week ends", "inflows_usd": "Money in (USD)", "outflows_usd": "Money out (USD)",
    "net_usd": "Net (USD)", "closing_available_usd": "Available cash at end (USD)", "lowest_available_usd": "Lowest available cash (USD)",
    "days_below_buffer": "Days below buffer", "scenario_id": "Scenario", "opening_available_usd": "Available cash at start (USD)",
    "lowest_on": "Lowest on", "entities_below_buffer": "Entities below buffer", "funding_gap_usd": "Funding gap (USD)",
    "lowest_vs_base_usd": "Lowest cash vs base (USD)", "funding_gap_vs_base_usd": "Funding gap vs base (USD)",
    "first_breach": "First breach", "max_shortfall_usd": "Largest shortfall (USD)", "apply_order": "Order", "assumption_id": "Assumption",
    "parameter": "What it changes", "filter_field": "Applies to", "filter_value": "Value", "value": "Setting", "unit": "Unit",
    "rationale": "Why", "reason": "Reason", "items_affected": "Items changed", "delta_net_flow_usd": "Effect on net cash flow (USD)",
    "delta_min_available_usd": "Effect on lowest cash (USD)", "cf_id": "Forecast item", "direction": "Direction", "flow_category": "Type of flow",
    "source_system": "Source", "counterparty_id": "Counterparty", "source_reference": "Reference", "risk_tier": "Customer risk tier",
    "treatment": "How it was handled", "date": "Expected date", "base_date": "Date in base case", "shifted_days": "Days moved by scenario",
    "currency_used": "Currency", "amount_local": "Amount (own currency)", "usd": "Amount (USD)", "signed_usd": "Cash effect (USD)",
    "exception_id": "Exception", "rule_id": "Rule", "exception_type": "Problem", "category": "Category", "severity": "Severity",
    "status_at_end": "Status", "run_id": "Forecast run", "record_table": "Record type", "record_id": "Record", "related_record_id": "Related record",
    "impact_usd": "Estimated impact (USD)", "decision": "Decision taken", "detected_at": "Detected at",
    "change_type": "Change", "what_happened": "What happened", "reference": "Reference", "date_a": "Date in earlier run",
    "date_b": "Date in this run", "net_usd_a": "Cash effect, earlier run (USD)", "net_usd_b": "Cash effect, this run (USD)", "change_usd": "Change (USD)",
    "rate_a": "Rate, earlier run", "rate_b": "Rate, this run", "change_pct": "Change (%)",
    "forecast_net_usd": "Forecast net cash (USD)", "actual_net_usd": "Actual net cash (USD)", "variance_usd": "Difference: actual - forecast (USD)",
    "timing_usd": "Timing (USD)", "amount_usd": "Amount (USD)", "fx_usd": "FX rates (USD)", "new_after_cutoff_usd": "New business after the forecast (USD)",
    "unforecasted_usd": "Never forecast (USD)", "not_realized_usd": "Did not happen (USD)", "run_rate_usd": "Small daily flows (USD)",
    "data_quality_usd": "Data-quality rules (USD)", "residual_usd": "Unexplained (USD)", "event_ts": "When", "event_type": "Event",
    "from_status": "From", "to_status": "To", "actor_id": "Who", "comment": "Comment", "action": "Action", "outcome": "Outcome", "detail": "Detail",
    "items": "Items", "path": "File", "rows": "Rows", "bytes": "Bytes", "sha256": "SHA-256 checksum", "posting_date": "Date",
    "ledger_entry_id": "Ledger entry", "entry_type": "Type", "description": "Description", "money_in": "Money in", "money_out": "Money out",
    "counterparty": "Counterparty", "country_code": "Country", "functional_currency": "Currency", "entity_type": "Type", "parent_entity_id": "Owned by",
    "min_liquidity_buffer": "Minimum buffer", "effective_from": "In the group from", "effective_to": "In the group until", "status": "Status",
    "overdraft_limit": "Overdraft limit", "opened_on": "Opened", "closed_on": "Closed", "opening_balance": "Opening balance",
    "opening_balance_date": "Opening balance on", "is_pool_header": "Cash-pool header?", "receivable_id": "Invoice", "invoice_number": "Invoice number",
    "invoice_date": "Invoice date", "due_date": "Due date", "customer": "Customer", "supplier": "Supplier", "paid_on": "Paid on",
    "days_late": "Days late (paid)", "payable_id": "Bill", "bill_number": "Bill number", "bill_date": "Bill date", "is_one_off": "Large one-off?",
    "payment_terms_days": "Payment terms (days)", "invoices": "Invoices", "paid": "Paid", "median_days_late": "Typical days late",
    "share_paid_over_7_days_late": "Paid more than 7 days late", "written_off": "Written off", "still_unpaid": "Still unpaid",
    "scenarios": "Scenarios", "role": "Role", "people": "People", "can_do": "What they can do", "records_authored": "Records they created",
    "denied_attempts": "Attempts refused", "item": "Item", "brief_baseline": "Required by the brief", "this_dataset": "In this dataset",
    "result": "Result", "found": "Found in this dataset", "what_it_means": "What it means", "how_handled": "How CashPilot handles it",
    "where": "Where to look", "edge_case": "Edge case", "criterion": "Acceptance criterion", "proof": "Evidence", "status_text": "Status",
}
HELP = {
    "headroom_usd": "Available cash minus the minimum buffer. Negative means a shortfall.",
    "fx_status": "OK = rate available. FALLBACK = previous rate used. MISSING = no usable rate. INCOMPLETE = a balance could not be converted.",
    "shifted_days": "How many days the scenario moved this item compared with the base case.",
    "treatment": "How the run handled this item (used as recorded, moved, dropped, converted).",
    "funding_gap_usd": "Sum of the entities' largest shortfalls below their buffers.",
    "bank_minus_book_local": "Difference between the bank statement and the ledger. Zero when they agree.",
    "residual_usd": "Part of the variance no driver explains. Always zero.",
}


# Friendly names for what CashPilot raises, and for why a forecast run exists
EXCEPTION_NAME = {
    "BALANCE_BREAK": "Bank and ledger do not agree",
    "FX_RATE_MISSING": "FX rate missing",
    "DUPLICATE_CASH_FLOW": "Cash flow counted twice",
    "LOOKAHEAD_LEAKAGE": "Forecast used data from after its cutoff",
    "MIXED_CURRENCY": "Currency mixed without conversion",
    "LIQUIDITY_BREACH": "Projected cash below the buffer (alert)",
}
PURPOSE_TEXT = {"SCHEDULED": "weekly", "RERUN": "re-run", "REMEDIATION": "corrected re-run", "LIVE": "live"}

FLOW_LABEL = {
    "AR_COLLECTION": "Customer receipts", "AP_PAYMENT": "Supplier payments", "PAYROLL": "Payroll", "RENT": "Rent", "TAX": "Tax",
    "DEBT_SERVICE": "Debt service", "OPERATING_RUN_RATE": "Small daily flows (run-rate)", "OTHER": "Manual items",
}
