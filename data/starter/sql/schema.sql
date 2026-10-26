-- CashPilot schema, generated from src/cashpilot/schema/dictionary.yaml.
-- Tables are ordered parents-first so the file can be applied top to bottom.

-- ISO 4217 currencies in scope. Minor units drive rounding and formatting.
CREATE TABLE currency (
    currency_code TEXT NOT NULL CHECK (currency_code IN ('USD', 'EUR', 'GBP', 'INR', 'JPY')),
    currency_name TEXT NOT NULL,
    minor_units INTEGER NOT NULL CHECK (minor_units IN (0, 2)),
    is_reporting_currency BOOLEAN NOT NULL,
    PRIMARY KEY (currency_code)
);

-- Fictional customers and suppliers. Customer risk tier drives payment behaviour.
CREATE TABLE counterparty (
    counterparty_id TEXT NOT NULL,
    counterparty_name TEXT NOT NULL,
    counterparty_type TEXT NOT NULL CHECK (counterparty_type IN ('CUSTOMER', 'SUPPLIER')),
    country_code TEXT NOT NULL CHECK (country_code IN ('US', 'DE', 'NL', 'FR', 'GB', 'IN', 'JP')),
    default_currency TEXT NOT NULL,
    risk_tier TEXT NOT NULL CHECK (risk_tier IN ('A', 'B', 'C', 'D')),
    payment_terms_days INTEGER NOT NULL CHECK (payment_terms_days IN (15, 30, 45, 60, 90)),
    PRIMARY KEY (counterparty_id),
    FOREIGN KEY (default_currency) REFERENCES currency (currency_code)
);

-- Daily closing FX rates against USD, one per business day and currency.
CREATE TABLE currency_rate (
    rate_id TEXT NOT NULL,
    rate_date DATE NOT NULL,
    base_currency TEXT NOT NULL CHECK (base_currency IN ('EUR', 'GBP', 'INR', 'JPY')),
    quote_currency TEXT NOT NULL CHECK (quote_currency IN ('USD')),
    rate NUMERIC(18,8) NOT NULL,
    rate_type TEXT NOT NULL CHECK (rate_type IN ('CLOSING')),
    source TEXT NOT NULL CHECK (source IN ('SYNTHETIC_GBM')),
    recorded_at TIMESTAMP NOT NULL,
    PRIMARY KEY (rate_id),
    UNIQUE (rate_date, base_currency, quote_currency),
    FOREIGN KEY (base_currency) REFERENCES currency (currency_code),
    FOREIGN KEY (quote_currency) REFERENCES currency (currency_code)
);

-- Documented, parameterised assumptions. Scenarios differ only through these rows.
CREATE TABLE scenario_assumption (
    assumption_id TEXT NOT NULL,
    parameter TEXT NOT NULL CHECK (parameter IN ('AR_DELAY_DAYS', 'AR_COLLECTION_RATE', 'AP_TIMING_SHIFT_DAYS', 'RUN_RATE_INFLOW_FACTOR', 'FX_SHOCK_PCT')),
    filter_field TEXT CHECK (filter_field IN ('risk_tier', 'currency_not')),
    filter_value TEXT,
    value NUMERIC(18,6) NOT NULL,
    unit TEXT NOT NULL CHECK (unit IN ('days', 'ratio', 'pct')),
    rationale TEXT NOT NULL,
    PRIMARY KEY (assumption_id)
);

-- Companies in the group. One holding company owns every operating entity.
CREATE TABLE legal_entity (
    entity_id TEXT NOT NULL,
    entity_name TEXT NOT NULL,
    country_code TEXT NOT NULL CHECK (country_code IN ('US', 'DE', 'NL', 'FR', 'GB', 'IN', 'JP')),
    functional_currency TEXT NOT NULL,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('HOLDING', 'OPERATING')),
    parent_entity_id TEXT,
    size_tier TEXT NOT NULL CHECK (size_tier IN ('S', 'M', 'L')),
    min_liquidity_buffer NUMERIC(20,2) NOT NULL,
    effective_from DATE NOT NULL,
    effective_to DATE,
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'INACTIVE')),
    PRIMARY KEY (entity_id),
    FOREIGN KEY (functional_currency) REFERENCES currency (currency_code),
    FOREIGN KEY (parent_entity_id) REFERENCES legal_entity (entity_id)
);

-- Bank accounts held by the entities. Pool headers concentrate cash per currency.
CREATE TABLE bank_account (
    account_id TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    bank_name TEXT NOT NULL,
    account_number_masked TEXT NOT NULL,
    currency TEXT NOT NULL,
    account_type TEXT NOT NULL CHECK (account_type IN ('CONCENTRATION', 'OPERATING', 'COLLECTION', 'PAYROLL', 'DEPOSIT', 'RESTRICTED')),
    is_restricted BOOLEAN NOT NULL,
    is_pool_header BOOLEAN NOT NULL,
    overdraft_limit NUMERIC(20,2) NOT NULL,
    opened_on DATE NOT NULL,
    opening_balance_date DATE NOT NULL,
    opening_balance NUMERIC(20,2) NOT NULL,
    closed_on DATE,
    status_at_end TEXT NOT NULL CHECK (status_at_end IN ('ACTIVE', 'FROZEN', 'CLOSED')),
    PRIMARY KEY (account_id),
    FOREIGN KEY (entity_id) REFERENCES legal_entity (entity_id),
    FOREIGN KEY (currency) REFERENCES currency (currency_code)
);

-- Customer invoices (accounts receivable) with expected collection dates.
CREATE TABLE receivable (
    receivable_id TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    counterparty_id TEXT NOT NULL,
    invoice_number TEXT NOT NULL,
    invoice_date DATE NOT NULL,
    due_date DATE NOT NULL,
    currency TEXT NOT NULL,
    amount NUMERIC(20,2) NOT NULL,
    recorded_at TIMESTAMP NOT NULL,
    status_at_end TEXT NOT NULL CHECK (status_at_end IN ('OPEN', 'PARTIALLY_PAID', 'OVERDUE', 'PAID', 'WRITTEN_OFF')),
    PRIMARY KEY (receivable_id),
    UNIQUE (invoice_number),
    FOREIGN KEY (entity_id) REFERENCES legal_entity (entity_id),
    FOREIGN KEY (account_id) REFERENCES bank_account (account_id),
    FOREIGN KEY (counterparty_id) REFERENCES counterparty (counterparty_id),
    FOREIGN KEY (currency) REFERENCES currency (currency_code)
);

-- Supplier bills and large one-off obligations (accounts payable).
CREATE TABLE payable (
    payable_id TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    counterparty_id TEXT NOT NULL,
    bill_number TEXT NOT NULL,
    bill_date DATE NOT NULL,
    due_date DATE NOT NULL,
    currency TEXT NOT NULL,
    amount NUMERIC(20,2) NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('TRADE', 'CAPEX', 'ACQUISITION', 'DEBT_REPAYMENT', 'TAX_SETTLEMENT', 'LEGAL_SETTLEMENT')),
    is_one_off BOOLEAN NOT NULL,
    recorded_at TIMESTAMP NOT NULL,
    status_at_end TEXT NOT NULL CHECK (status_at_end IN ('SCHEDULED', 'APPROVED', 'ON_HOLD', 'PAID', 'CANCELLED')),
    PRIMARY KEY (payable_id),
    UNIQUE (bill_number),
    FOREIGN KEY (entity_id) REFERENCES legal_entity (entity_id),
    FOREIGN KEY (account_id) REFERENCES bank_account (account_id),
    FOREIGN KEY (counterparty_id) REFERENCES counterparty (counterparty_id),
    FOREIGN KEY (currency) REFERENCES currency (currency_code)
);

-- Daily statements as reported by the banks (the bank's view of each account).
CREATE TABLE bank_statement (
    statement_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    statement_date DATE NOT NULL,
    currency TEXT NOT NULL,
    opening_balance NUMERIC(20,2) NOT NULL,
    total_credits NUMERIC(20,2) NOT NULL,
    total_debits NUMERIC(20,2) NOT NULL,
    closing_balance NUMERIC(20,2) NOT NULL,
    transaction_count INTEGER NOT NULL,
    recorded_at TIMESTAMP NOT NULL,
    PRIMARY KEY (statement_id),
    UNIQUE (account_id, statement_date),
    FOREIGN KEY (account_id) REFERENCES bank_account (account_id),
    FOREIGN KEY (currency) REFERENCES currency (currency_code)
);

-- Actual daily position per account from the ledger, with the bank's view and USD value.
CREATE TABLE daily_cash_position (
    account_id TEXT NOT NULL,
    position_date DATE NOT NULL,
    entity_id TEXT NOT NULL,
    currency TEXT NOT NULL,
    opening_balance NUMERIC(20,2) NOT NULL,
    inflows NUMERIC(20,2) NOT NULL,
    outflows NUMERIC(20,2) NOT NULL,
    closing_balance NUMERIC(20,2) NOT NULL,
    statement_closing NUMERIC(20,2),
    bank_minus_book NUMERIC(20,2),
    fx_rate_id TEXT,
    fx_status TEXT NOT NULL CHECK (fx_status IN ('NOT_REQUIRED', 'OK', 'FALLBACK', 'MISSING')),
    closing_balance_usd NUMERIC(20,2),
    PRIMARY KEY (account_id, position_date),
    FOREIGN KEY (account_id) REFERENCES bank_account (account_id),
    FOREIGN KEY (entity_id) REFERENCES legal_entity (entity_id),
    FOREIGN KEY (currency) REFERENCES currency (currency_code),
    FOREIGN KEY (fx_rate_id) REFERENCES currency_rate (rate_id)
);

-- Consolidated actual daily cash per entity in USD.
CREATE TABLE entity_cash_position (
    entity_id TEXT NOT NULL,
    position_date DATE NOT NULL,
    total_usd NUMERIC(20,2) NOT NULL,
    available_usd NUMERIC(20,2) NOT NULL,
    restricted_usd NUMERIC(20,2) NOT NULL,
    min_buffer_usd NUMERIC(20,2) NOT NULL,
    headroom_usd NUMERIC(20,2) NOT NULL,
    fx_status TEXT NOT NULL CHECK (fx_status IN ('OK', 'FALLBACK', 'INCOMPLETE')),
    accounts_active INTEGER NOT NULL,
    PRIMARY KEY (entity_id, position_date),
    FOREIGN KEY (entity_id) REFERENCES legal_entity (entity_id)
);

-- Synthetic users acting in the workflow. Names are role labels, not people.
CREATE TABLE app_user (
    user_id TEXT NOT NULL,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('SYSTEM', 'SYS_ADMIN', 'OPS_ANALYST', 'RISK_REVIEWER', 'ACCOUNT_HOLDER')),
    entity_id TEXT,
    active_from DATE NOT NULL,
    PRIMARY KEY (user_id),
    FOREIGN KEY (entity_id) REFERENCES legal_entity (entity_id)
);

-- Versioned liquidity scenarios. A scenario is defined only by its linked assumptions.
CREATE TABLE liquidity_scenario (
    scenario_id TEXT NOT NULL,
    scenario_code TEXT NOT NULL CHECK (scenario_code IN ('BASE', 'DELAY', 'STRESS')),
    version INTEGER NOT NULL,
    scenario_name TEXT NOT NULL,
    description TEXT NOT NULL,
    effective_from DATE NOT NULL,
    effective_to DATE,
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'RETIRED')),
    supersedes_scenario_id TEXT,
    created_by TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    PRIMARY KEY (scenario_id),
    FOREIGN KEY (supersedes_scenario_id) REFERENCES liquidity_scenario (scenario_id),
    FOREIGN KEY (created_by) REFERENCES app_user (user_id)
);

-- Which assumptions make up each scenario version, in application order.
CREATE TABLE scenario_assumption_link (
    scenario_id TEXT NOT NULL,
    assumption_id TEXT NOT NULL,
    apply_order INTEGER NOT NULL,
    PRIMARY KEY (scenario_id, assumption_id),
    FOREIGN KEY (scenario_id) REFERENCES liquidity_scenario (scenario_id),
    FOREIGN KEY (assumption_id) REFERENCES scenario_assumption (assumption_id)
);

-- Expected cash-flow items: subledger feeds, recurring schedules, run-rate estimates and manual submissions.
CREATE TABLE cash_flow_forecast (
    cf_id TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('INFLOW', 'OUTFLOW')),
    flow_category TEXT NOT NULL CHECK (flow_category IN ('AR_COLLECTION', 'AP_PAYMENT', 'PAYROLL', 'RENT', 'TAX', 'DEBT_SERVICE', 'OPERATING_RUN_RATE', 'OTHER')),
    source_system TEXT NOT NULL CHECK (source_system IN ('AR_SUBLEDGER', 'AP_SUBLEDGER', 'PAYROLL_SYSTEM', 'LEASE_SYSTEM', 'TAX_CALENDAR', 'LOAN_SYSTEM', 'RUN_RATE_MODEL', 'MANUAL')),
    receivable_id TEXT,
    payable_id TEXT,
    counterparty_id TEXT,
    source_reference TEXT,
    currency TEXT NOT NULL,
    amount NUMERIC(20,2) NOT NULL,
    original_currency TEXT,
    original_amount NUMERIC(20,2),
    fx_rate_id TEXT,
    expected_date DATE NOT NULL,
    recorded_at TIMESTAMP NOT NULL,
    created_by TEXT NOT NULL,
    PRIMARY KEY (cf_id),
    FOREIGN KEY (entity_id) REFERENCES legal_entity (entity_id),
    FOREIGN KEY (account_id) REFERENCES bank_account (account_id),
    FOREIGN KEY (receivable_id) REFERENCES receivable (receivable_id),
    FOREIGN KEY (payable_id) REFERENCES payable (payable_id),
    FOREIGN KEY (counterparty_id) REFERENCES counterparty (counterparty_id),
    FOREIGN KEY (currency) REFERENCES currency (currency_code),
    FOREIGN KEY (original_currency) REFERENCES currency (currency_code),
    FOREIGN KEY (fx_rate_id) REFERENCES currency_rate (rate_id),
    FOREIGN KEY (created_by) REFERENCES app_user (user_id)
);

-- Booked cash movements (actuals). Positive = inflow, negative = outflow, in account currency.
CREATE TABLE ledger_entry (
    ledger_entry_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    posting_date DATE NOT NULL,
    recorded_at TIMESTAMP NOT NULL,
    currency TEXT NOT NULL,
    amount NUMERIC(20,2) NOT NULL,
    entry_type TEXT NOT NULL CHECK (entry_type IN ('AR_RECEIPT', 'AP_PAYMENT', 'PAYROLL', 'RENT', 'TAX', 'DEBT_SERVICE', 'BANK_FEE', 'INTEREST', 'OPERATING_RECEIPT', 'OPERATING_PAYMENT', 'OTHER_RECEIPT', 'OTHER_PAYMENT', 'POOL_SWEEP', 'POOL_FUNDING', 'FX_CONVERSION', 'ACCOUNT_CLOSURE')),
    cf_id TEXT,
    counterparty_id TEXT,
    transfer_group_id TEXT,
    fx_rate_id TEXT,
    original_currency TEXT,
    original_amount NUMERIC(20,2),
    description TEXT NOT NULL,
    PRIMARY KEY (ledger_entry_id),
    FOREIGN KEY (account_id) REFERENCES bank_account (account_id),
    FOREIGN KEY (entity_id) REFERENCES legal_entity (entity_id),
    FOREIGN KEY (currency) REFERENCES currency (currency_code),
    FOREIGN KEY (cf_id) REFERENCES cash_flow_forecast (cf_id),
    FOREIGN KEY (counterparty_id) REFERENCES counterparty (counterparty_id),
    FOREIGN KEY (fx_rate_id) REFERENCES currency_rate (rate_id),
    FOREIGN KEY (original_currency) REFERENCES currency (currency_code)
);

-- How cash postings settle invoices and bills: one transfer may pay several invoices, one invoice may be paid in parts.
CREATE TABLE settlement_allocation (
    settlement_id TEXT NOT NULL,
    ledger_entry_id TEXT NOT NULL,
    receivable_id TEXT,
    payable_id TEXT,
    currency TEXT NOT NULL,
    allocated_amount NUMERIC(20,2) NOT NULL,
    allocation_date DATE NOT NULL,
    PRIMARY KEY (settlement_id),
    FOREIGN KEY (ledger_entry_id) REFERENCES ledger_entry (ledger_entry_id),
    FOREIGN KEY (receivable_id) REFERENCES receivable (receivable_id),
    FOREIGN KEY (payable_id) REFERENCES payable (payable_id),
    FOREIGN KEY (currency) REFERENCES currency (currency_code)
);

-- Account lifecycle history (append-only).
CREATE TABLE bank_account_event (
    event_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    event_ts TIMESTAMP NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('OPENED', 'FROZEN', 'UNFROZEN', 'CLOSED')),
    from_status TEXT CHECK (from_status IN ('ACTIVE', 'FROZEN')),
    to_status TEXT NOT NULL CHECK (to_status IN ('ACTIVE', 'FROZEN', 'CLOSED')),
    actor_id TEXT NOT NULL,
    reason TEXT,
    PRIMARY KEY (event_id),
    FOREIGN KEY (account_id) REFERENCES bank_account (account_id),
    FOREIGN KEY (actor_id) REFERENCES app_user (user_id)
);

-- Invoice lifecycle history (append-only).
CREATE TABLE receivable_event (
    event_id TEXT NOT NULL,
    receivable_id TEXT NOT NULL,
    event_ts TIMESTAMP NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('CREATED', 'PARTIAL_PAYMENT', 'OVERDUE', 'PAID', 'WRITTEN_OFF')),
    from_status TEXT CHECK (from_status IN ('OPEN', 'PARTIALLY_PAID', 'OVERDUE')),
    to_status TEXT NOT NULL CHECK (to_status IN ('OPEN', 'PARTIALLY_PAID', 'OVERDUE', 'PAID', 'WRITTEN_OFF')),
    currency TEXT NOT NULL,
    amount NUMERIC(20,2),
    ledger_entry_id TEXT,
    actor_id TEXT NOT NULL,
    PRIMARY KEY (event_id),
    FOREIGN KEY (receivable_id) REFERENCES receivable (receivable_id),
    FOREIGN KEY (currency) REFERENCES currency (currency_code),
    FOREIGN KEY (ledger_entry_id) REFERENCES ledger_entry (ledger_entry_id),
    FOREIGN KEY (actor_id) REFERENCES app_user (user_id)
);

-- Bill lifecycle history (append-only).
CREATE TABLE payable_event (
    event_id TEXT NOT NULL,
    payable_id TEXT NOT NULL,
    event_ts TIMESTAMP NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('CREATED', 'APPROVED', 'HELD', 'RELEASED', 'PAID', 'CANCELLED')),
    from_status TEXT CHECK (from_status IN ('SCHEDULED', 'APPROVED', 'ON_HOLD')),
    to_status TEXT NOT NULL CHECK (to_status IN ('SCHEDULED', 'APPROVED', 'ON_HOLD', 'PAID', 'CANCELLED')),
    ledger_entry_id TEXT,
    actor_id TEXT NOT NULL,
    PRIMARY KEY (event_id),
    FOREIGN KEY (payable_id) REFERENCES payable (payable_id),
    FOREIGN KEY (ledger_entry_id) REFERENCES ledger_entry (ledger_entry_id),
    FOREIGN KEY (actor_id) REFERENCES app_user (user_id)
);

-- Later changes to forecast items (new date, new amount, settled, cancelled). Items themselves never change.
CREATE TABLE cf_revision (
    revision_id TEXT NOT NULL,
    cf_id TEXT NOT NULL,
    revision_no INTEGER NOT NULL,
    recorded_at TIMESTAMP NOT NULL,
    revision_type TEXT NOT NULL CHECK (revision_type IN ('DATE_CHANGE', 'AMOUNT_CHANGE', 'SETTLED', 'CANCELLED')),
    new_expected_date DATE,
    currency TEXT NOT NULL,
    new_amount NUMERIC(20,2),
    reason TEXT NOT NULL CHECK (reason IN ('CUSTOMER_ADVISED_DELAY', 'PARTIAL_PAYMENT', 'PAID_IN_FULL', 'WRITTEN_OFF', 'SUPPLIER_HOLD', 'HOLD_RELEASED', 'PAYMENT_DEFERRED', 'PAYMENT_CANCELLED', 'RUN_RATE_REESTIMATE', 'REALIZED', 'NOT_REALIZED')),
    actor_id TEXT NOT NULL,
    PRIMARY KEY (revision_id),
    UNIQUE (cf_id, revision_no),
    FOREIGN KEY (cf_id) REFERENCES cash_flow_forecast (cf_id),
    FOREIGN KEY (currency) REFERENCES currency (currency_code),
    FOREIGN KEY (actor_id) REFERENCES app_user (user_id)
);

-- Forecast versions. Each run is an immutable 13-week projection as of a cutoff.
CREATE TABLE forecast_run (
    run_id TEXT NOT NULL,
    cutoff_date DATE NOT NULL,
    knowledge_cutoff_ts TIMESTAMP NOT NULL,
    horizon_start DATE NOT NULL,
    horizon_end DATE NOT NULL,
    horizon_days INTEGER NOT NULL,
    version INTEGER NOT NULL,
    supersedes_run_id TEXT,
    process TEXT NOT NULL CHECK (process IN ('LEGACY', 'CASHPILOT')),
    run_purpose TEXT NOT NULL CHECK (run_purpose IN ('SCHEDULED', 'RERUN', 'REMEDIATION', 'LIVE')),
    reporting_currency TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    input_hash TEXT NOT NULL,
    result_hash TEXT NOT NULL,
    status_at_end TEXT NOT NULL CHECK (status_at_end IN ('CREATED', 'COMPLETED', 'SUBMITTED', 'APPROVED', 'REJECTED', 'SUPERSEDED')),
    PRIMARY KEY (run_id),
    FOREIGN KEY (supersedes_run_id) REFERENCES forecast_run (run_id),
    FOREIGN KEY (reporting_currency) REFERENCES currency (currency_code),
    FOREIGN KEY (created_by) REFERENCES app_user (user_id)
);

-- Forecast run lifecycle history (append-only).
CREATE TABLE forecast_run_event (
    event_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    event_ts TIMESTAMP NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('CREATED', 'COMPLETED', 'SUBMITTED', 'APPROVED', 'REJECTED', 'SUPERSEDED')),
    from_status TEXT CHECK (from_status IN ('CREATED', 'COMPLETED', 'SUBMITTED', 'APPROVED')),
    to_status TEXT NOT NULL CHECK (to_status IN ('CREATED', 'COMPLETED', 'SUBMITTED', 'APPROVED', 'REJECTED', 'SUPERSEDED')),
    actor_id TEXT NOT NULL,
    comment TEXT,
    PRIMARY KEY (event_id),
    FOREIGN KEY (run_id) REFERENCES forecast_run (run_id),
    FOREIGN KEY (actor_id) REFERENCES app_user (user_id)
);

-- Scenarios evaluated in each run.
CREATE TABLE forecast_run_scenario (
    run_id TEXT NOT NULL,
    scenario_id TEXT NOT NULL,
    PRIMARY KEY (run_id, scenario_id),
    FOREIGN KEY (run_id) REFERENCES forecast_run (run_id),
    FOREIGN KEY (scenario_id) REFERENCES liquidity_scenario (scenario_id)
);

-- Input lineage: every forecast item a run considered, the revision it used and how it was treated.
CREATE TABLE forecast_run_item (
    run_id TEXT NOT NULL,
    cf_id TEXT NOT NULL,
    revision_id TEXT,
    input_recorded_at TIMESTAMP NOT NULL,
    treatment TEXT NOT NULL CHECK (treatment IN ('INCLUDED', 'OVERDUE_ROLLED', 'EXCLUDED_STALE', 'EXCLUDED_DUPLICATE', 'CONVERTED', 'QUARANTINED')),
    expected_date_used DATE,
    currency TEXT NOT NULL,
    amount_used NUMERIC(20,2) NOT NULL,
    PRIMARY KEY (run_id, cf_id),
    FOREIGN KEY (run_id) REFERENCES forecast_run (run_id),
    FOREIGN KEY (cf_id) REFERENCES cash_flow_forecast (cf_id),
    FOREIGN KEY (revision_id) REFERENCES cf_revision (revision_id),
    FOREIGN KEY (currency) REFERENCES currency (currency_code)
);

-- Input lineage: the bank statement each run used as an account's opening balance.
CREATE TABLE forecast_run_balance_input (
    run_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    statement_id TEXT NOT NULL,
    statement_date DATE NOT NULL,
    currency TEXT NOT NULL,
    balance_used NUMERIC(20,2) NOT NULL,
    PRIMARY KEY (run_id, account_id),
    FOREIGN KEY (run_id) REFERENCES forecast_run (run_id),
    FOREIGN KEY (account_id) REFERENCES bank_account (account_id),
    FOREIGN KEY (statement_id) REFERENCES bank_statement (statement_id),
    FOREIGN KEY (currency) REFERENCES currency (currency_code)
);

-- Input lineage: the FX rate each run used per currency.
CREATE TABLE forecast_run_fx_input (
    run_id TEXT NOT NULL,
    currency_code TEXT NOT NULL,
    rate_id TEXT NOT NULL,
    rate_date DATE NOT NULL,
    rate_used NUMERIC(18,8) NOT NULL,
    PRIMARY KEY (run_id, currency_code),
    FOREIGN KEY (run_id) REFERENCES forecast_run (run_id),
    FOREIGN KEY (currency_code) REFERENCES currency (currency_code),
    FOREIGN KEY (rate_id) REFERENCES currency_rate (rate_id)
);

-- Run results: projected daily available cash per entity and scenario, in USD.
CREATE TABLE forecast_position (
    run_id TEXT NOT NULL,
    scenario_id TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    position_date DATE NOT NULL,
    opening_available_usd NUMERIC(20,2) NOT NULL,
    inflows_usd NUMERIC(20,2) NOT NULL,
    outflows_usd NUMERIC(20,2) NOT NULL,
    closing_available_usd NUMERIC(20,2) NOT NULL,
    restricted_usd NUMERIC(20,2) NOT NULL,
    min_buffer_usd NUMERIC(20,2) NOT NULL,
    breach_flag BOOLEAN NOT NULL,
    PRIMARY KEY (run_id, scenario_id, entity_id, position_date),
    FOREIGN KEY (run_id) REFERENCES forecast_run (run_id),
    FOREIGN KEY (scenario_id) REFERENCES liquidity_scenario (scenario_id),
    FOREIGN KEY (entity_id) REFERENCES legal_entity (entity_id)
);

-- Contribution of each assumption to a scenario, applied in order (proves scenarios differ only by documented assumptions).
CREATE TABLE scenario_assumption_effect (
    run_id TEXT NOT NULL,
    scenario_id TEXT NOT NULL,
    assumption_id TEXT NOT NULL,
    apply_order INTEGER NOT NULL,
    items_affected INTEGER NOT NULL,
    delta_net_flow_usd NUMERIC(20,2) NOT NULL,
    delta_min_available_usd NUMERIC(20,2) NOT NULL,
    PRIMARY KEY (run_id, scenario_id, assumption_id),
    FOREIGN KEY (run_id) REFERENCES forecast_run (run_id),
    FOREIGN KEY (scenario_id) REFERENCES liquidity_scenario (scenario_id),
    FOREIGN KEY (assumption_id) REFERENCES scenario_assumption (assumption_id)
);

-- Actual-versus-forecast per run, scenario, entity and week, with the variance split into drivers.
CREATE TABLE forecast_vs_actual (
    run_id TEXT NOT NULL,
    scenario_id TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    week_no INTEGER NOT NULL,
    week_start DATE NOT NULL,
    week_end DATE NOT NULL,
    forecast_net_usd NUMERIC(20,2) NOT NULL,
    actual_net_usd NUMERIC(20,2) NOT NULL,
    variance_usd NUMERIC(20,2) NOT NULL,
    timing_usd NUMERIC(20,2) NOT NULL,
    amount_usd NUMERIC(20,2) NOT NULL,
    fx_usd NUMERIC(20,2) NOT NULL,
    new_after_cutoff_usd NUMERIC(20,2) NOT NULL,
    unforecasted_usd NUMERIC(20,2) NOT NULL,
    not_realized_usd NUMERIC(20,2) NOT NULL,
    run_rate_usd NUMERIC(20,2) NOT NULL,
    data_quality_usd NUMERIC(20,2) NOT NULL,
    residual_usd NUMERIC(20,2) NOT NULL,
    PRIMARY KEY (run_id, scenario_id, entity_id, week_no),
    FOREIGN KEY (run_id) REFERENCES forecast_run (run_id),
    FOREIGN KEY (scenario_id) REFERENCES liquidity_scenario (scenario_id),
    FOREIGN KEY (entity_id) REFERENCES legal_entity (entity_id)
);

-- Item-level drill-down of the base-scenario variance.
CREATE TABLE variance_attribution (
    attribution_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    scenario_id TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    week_no INTEGER NOT NULL,
    driver TEXT NOT NULL CHECK (driver IN ('TIMING', 'AMOUNT', 'FX', 'NEW_AFTER_CUTOFF', 'UNFORECASTED', 'NOT_REALIZED', 'RUN_RATE', 'DATA_QUALITY')),
    cf_id TEXT,
    ledger_entry_id TEXT,
    amount_usd NUMERIC(20,2) NOT NULL,
    PRIMARY KEY (attribution_id),
    FOREIGN KEY (run_id) REFERENCES forecast_run (run_id),
    FOREIGN KEY (scenario_id) REFERENCES liquidity_scenario (scenario_id),
    FOREIGN KEY (entity_id) REFERENCES legal_entity (entity_id),
    FOREIGN KEY (cf_id) REFERENCES cash_flow_forecast (cf_id),
    FOREIGN KEY (ledger_entry_id) REFERENCES ledger_entry (ledger_entry_id)
);

-- Exceptions raised by CashPilot rules, each with a rule ID and a decision.
CREATE TABLE exception (
    exception_id TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('DATA_QUALITY', 'BUSINESS_ALERT')),
    exception_type TEXT NOT NULL CHECK (exception_type IN ('BALANCE_BREAK', 'FX_RATE_MISSING', 'DUPLICATE_CASH_FLOW', 'LOOKAHEAD_LEAKAGE', 'MIXED_CURRENCY', 'LIQUIDITY_BREACH')),
    severity TEXT NOT NULL CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    record_table TEXT NOT NULL,
    record_id TEXT NOT NULL,
    related_record_id TEXT,
    entity_id TEXT,
    account_id TEXT,
    run_id TEXT,
    impact_usd NUMERIC(20,2),
    decision TEXT NOT NULL CHECK (decision IN ('RAISE_RECON_BREAK', 'USE_PREVIOUS_RATE', 'BLOCK_CONVERSION', 'EXCLUDE_DUPLICATE', 'CONVERT_AT_CUTOFF_RATE', 'QUARANTINE_ITEM', 'SUPERSEDE_WITH_RERUN', 'FUNDING_REVIEW')),
    details TEXT NOT NULL,
    detected_at TIMESTAMP NOT NULL,
    status_at_end TEXT NOT NULL CHECK (status_at_end IN ('OPEN', 'ASSIGNED', 'ESCALATED', 'RESOLVED', 'WAIVED')),
    PRIMARY KEY (exception_id),
    FOREIGN KEY (entity_id) REFERENCES legal_entity (entity_id),
    FOREIGN KEY (account_id) REFERENCES bank_account (account_id),
    FOREIGN KEY (run_id) REFERENCES forecast_run (run_id)
);

-- Exception workflow history (append-only).
CREATE TABLE exception_event (
    event_id TEXT NOT NULL,
    exception_id TEXT NOT NULL,
    event_ts TIMESTAMP NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('RAISED', 'ASSIGNED', 'ESCALATED', 'RESOLVED', 'WAIVED')),
    from_status TEXT CHECK (from_status IN ('OPEN', 'ASSIGNED', 'ESCALATED')),
    to_status TEXT NOT NULL CHECK (to_status IN ('OPEN', 'ASSIGNED', 'ESCALATED', 'RESOLVED', 'WAIVED')),
    actor_id TEXT NOT NULL,
    comment TEXT,
    PRIMARY KEY (event_id),
    FOREIGN KEY (exception_id) REFERENCES exception (exception_id),
    FOREIGN KEY (actor_id) REFERENCES app_user (user_id)
);

-- Every workflow action attempted through CashPilot, allowed or denied.
CREATE TABLE audit_event (
    event_id TEXT NOT NULL,
    event_ts TIMESTAMP NOT NULL,
    actor_id TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('VIEW_ENTITY', 'CREATE_RUN', 'SUBMIT_RUN', 'APPROVE_RUN', 'REJECT_RUN', 'SUPERSEDE_RUN', 'ASSIGN_EXCEPTION', 'ESCALATE_EXCEPTION', 'RESOLVE_EXCEPTION', 'WAIVE_EXCEPTION')),
    target_id TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('ALLOWED', 'DENIED')),
    detail TEXT,
    PRIMARY KEY (event_id),
    FOREIGN KEY (actor_id) REFERENCES app_user (user_id)
);
