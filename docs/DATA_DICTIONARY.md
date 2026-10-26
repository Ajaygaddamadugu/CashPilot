# Data dictionary

Generated from `src/cashpilot/schema/dictionary.yaml`, the single source of truth that also produces `sql/schema.sql` and drives the structural validators. Do not edit by hand.

**Conventions.** Dates are `YYYY-MM-DD`; timestamps are UTC `YYYY-MM-DDTHH:MM:SSZ`. Money is a fixed-decimal string in the stated currency, with ISO 4217 decimals (JPY has none); internally it is held as integer minor units. Rates are USD per one unit of the base currency, 8 decimals. `status_at_end` columns are derived from the matching event table as of the end of the actuals period; the event tables are the authoritative history.

## Tables

| Table | Layer | Grain | Primary key |
|---|---|---|---|
| [`currency`](#currency) | reference | One row per currency. | `currency_code` |
| [`app_user`](#app_user) | reference | One row per user. | `user_id` |
| [`counterparty`](#counterparty) | reference | One row per counterparty. | `counterparty_id` |
| [`currency_rate`](#currency_rate) | reference | One row per (rate_date, base_currency). | `rate_id` |
| [`liquidity_scenario`](#liquidity_scenario) | reference | One row per scenario version. | `scenario_id` |
| [`scenario_assumption`](#scenario_assumption) | reference | One row per assumption. | `assumption_id` |
| [`scenario_assumption_link`](#scenario_assumption_link) | bridge | One row per (scenario, assumption). | `scenario_id, assumption_id` |
| [`legal_entity`](#legal_entity) | master | One row per legal entity. | `entity_id` |
| [`bank_account`](#bank_account) | master | One row per account. | `account_id` |
| [`receivable`](#receivable) | transaction | One row per invoice. | `receivable_id` |
| [`payable`](#payable) | transaction | One row per bill. | `payable_id` |
| [`cash_flow_forecast`](#cash_flow_forecast) | transaction | One row per forecast item; later changes are cf_revision rows. | `cf_id` |
| [`ledger_entry`](#ledger_entry) | transaction | One row per posting. | `ledger_entry_id` |
| [`settlement_allocation`](#settlement_allocation) | bridge | One row per (ledger entry, document). | `settlement_id` |
| [`bank_statement`](#bank_statement) | transaction | One row per account and business day while the account is active. | `statement_id` |
| [`bank_account_event`](#bank_account_event) | event | One row per state change. | `event_id` |
| [`receivable_event`](#receivable_event) | event | One row per state change. | `event_id` |
| [`payable_event`](#payable_event) | event | One row per state change. | `event_id` |
| [`cf_revision`](#cf_revision) | event | One row per revision. | `revision_id` |
| [`forecast_run`](#forecast_run) | history | One row per run (cutoff date + version). | `run_id` |
| [`forecast_run_event`](#forecast_run_event) | event | One row per state change. | `event_id` |
| [`forecast_run_scenario`](#forecast_run_scenario) | bridge | One row per (run, scenario). | `run_id, scenario_id` |
| [`forecast_run_item`](#forecast_run_item) | bridge | One row per (run, forecast item). | `run_id, cf_id` |
| [`forecast_run_balance_input`](#forecast_run_balance_input) | history | One row per (run, account). | `run_id, account_id` |
| [`forecast_run_fx_input`](#forecast_run_fx_input) | history | One row per (run, currency). | `run_id, currency_code` |
| [`forecast_position`](#forecast_position) | history | One row per (run, scenario, entity, day). | `run_id, scenario_id, entity_id, position_date` |
| [`daily_cash_position`](#daily_cash_position) | derived | One row per account and calendar day while active. | `account_id, position_date` |
| [`entity_cash_position`](#entity_cash_position) | derived | One row per entity and calendar day. | `entity_id, position_date` |
| [`scenario_assumption_effect`](#scenario_assumption_effect) | derived | One row per (run, scenario, assumption). | `run_id, scenario_id, assumption_id` |
| [`forecast_vs_actual`](#forecast_vs_actual) | derived | One row per (run, scenario, entity, week) fully inside the actuals period. | `run_id, scenario_id, entity_id, week_no` |
| [`variance_attribution`](#variance_attribution) | derived | One row per (run, entity, week, driver, record). | `attribution_id` |
| [`exception`](#exception) | output | One row per (rule, record). | `exception_id` |
| [`exception_event`](#exception_event) | output | One row per state change. | `event_id` |
| [`audit_event`](#audit_event) | output | One row per attempted action. | `event_id` |
| [`anomaly_label`](#anomaly_label) | ground_truth | One row per labelled record. | `gt_id` |

Layers: **reference** — Reference data and configuration (currencies, users, counterparties, FX, scenarios). **master** — Master data created first: legal entities and bank accounts. **transaction** — Business documents and cash movements that reference master data. **event** — Append-only state-change history; current status is derived from it. **bridge** — Bridge tables resolving many-to-many relationships. **history** — Forecast versions and their input lineage, kept immutable. **derived** — Values CashPilot computes from source records (never sampled). **output** — Exceptions, workflow and audit records produced by CashPilot. **ground_truth** — Labels for injected anomalies, stored outside the dataset.

## Relationships

Every foreign key, with cardinality (child : parent) and whether the child must have a parent.

| Child column | Parent | Cardinality | Optional |
|---|---|---|---|
| `app_user.entity_id` | `legal_entity.entity_id` | N:1 | yes |
| `counterparty.default_currency` | `currency.currency_code` | N:1 | no |
| `currency_rate.base_currency` | `currency.currency_code` | N:1 | no |
| `currency_rate.quote_currency` | `currency.currency_code` | N:1 | no |
| `liquidity_scenario.supersedes_scenario_id` | `liquidity_scenario.scenario_id` | N:1 | yes |
| `liquidity_scenario.created_by` | `app_user.user_id` | N:1 | no |
| `scenario_assumption_link.scenario_id` | `liquidity_scenario.scenario_id` | N:1 | no |
| `scenario_assumption_link.assumption_id` | `scenario_assumption.assumption_id` | N:1 | no |
| `legal_entity.functional_currency` | `currency.currency_code` | N:1 | no |
| `legal_entity.parent_entity_id` | `legal_entity.entity_id` | N:1 | yes |
| `bank_account.entity_id` | `legal_entity.entity_id` | N:1 | no |
| `bank_account.currency` | `currency.currency_code` | N:1 | no |
| `receivable.entity_id` | `legal_entity.entity_id` | N:1 | no |
| `receivable.account_id` | `bank_account.account_id` | N:1 | no |
| `receivable.counterparty_id` | `counterparty.counterparty_id` | N:1 | no |
| `receivable.currency` | `currency.currency_code` | N:1 | no |
| `payable.entity_id` | `legal_entity.entity_id` | N:1 | no |
| `payable.account_id` | `bank_account.account_id` | N:1 | no |
| `payable.counterparty_id` | `counterparty.counterparty_id` | N:1 | no |
| `payable.currency` | `currency.currency_code` | N:1 | no |
| `cash_flow_forecast.entity_id` | `legal_entity.entity_id` | N:1 | no |
| `cash_flow_forecast.account_id` | `bank_account.account_id` | N:1 | no |
| `cash_flow_forecast.receivable_id` | `receivable.receivable_id` | N:1 | yes |
| `cash_flow_forecast.payable_id` | `payable.payable_id` | N:1 | yes |
| `cash_flow_forecast.counterparty_id` | `counterparty.counterparty_id` | N:1 | yes |
| `cash_flow_forecast.currency` | `currency.currency_code` | N:1 | no |
| `cash_flow_forecast.original_currency` | `currency.currency_code` | N:1 | yes |
| `cash_flow_forecast.fx_rate_id` | `currency_rate.rate_id` | N:1 | yes |
| `cash_flow_forecast.created_by` | `app_user.user_id` | N:1 | no |
| `ledger_entry.account_id` | `bank_account.account_id` | N:1 | no |
| `ledger_entry.entity_id` | `legal_entity.entity_id` | N:1 | no |
| `ledger_entry.currency` | `currency.currency_code` | N:1 | no |
| `ledger_entry.cf_id` | `cash_flow_forecast.cf_id` | N:1 | yes |
| `ledger_entry.counterparty_id` | `counterparty.counterparty_id` | N:1 | yes |
| `ledger_entry.fx_rate_id` | `currency_rate.rate_id` | N:1 | yes |
| `ledger_entry.original_currency` | `currency.currency_code` | N:1 | yes |
| `settlement_allocation.ledger_entry_id` | `ledger_entry.ledger_entry_id` | N:1 | no |
| `settlement_allocation.receivable_id` | `receivable.receivable_id` | N:1 | yes |
| `settlement_allocation.payable_id` | `payable.payable_id` | N:1 | yes |
| `settlement_allocation.currency` | `currency.currency_code` | N:1 | no |
| `bank_statement.account_id` | `bank_account.account_id` | N:1 | no |
| `bank_statement.currency` | `currency.currency_code` | N:1 | no |
| `bank_account_event.account_id` | `bank_account.account_id` | N:1 | no |
| `bank_account_event.actor_id` | `app_user.user_id` | N:1 | no |
| `receivable_event.receivable_id` | `receivable.receivable_id` | N:1 | no |
| `receivable_event.currency` | `currency.currency_code` | N:1 | no |
| `receivable_event.ledger_entry_id` | `ledger_entry.ledger_entry_id` | N:1 | yes |
| `receivable_event.actor_id` | `app_user.user_id` | N:1 | no |
| `payable_event.payable_id` | `payable.payable_id` | N:1 | no |
| `payable_event.ledger_entry_id` | `ledger_entry.ledger_entry_id` | N:1 | yes |
| `payable_event.actor_id` | `app_user.user_id` | N:1 | no |
| `cf_revision.cf_id` | `cash_flow_forecast.cf_id` | N:1 | no |
| `cf_revision.currency` | `currency.currency_code` | N:1 | no |
| `cf_revision.actor_id` | `app_user.user_id` | N:1 | no |
| `forecast_run.supersedes_run_id` | `forecast_run.run_id` | N:1 | yes |
| `forecast_run.reporting_currency` | `currency.currency_code` | N:1 | no |
| `forecast_run.created_by` | `app_user.user_id` | N:1 | no |
| `forecast_run_event.run_id` | `forecast_run.run_id` | N:1 | no |
| `forecast_run_event.actor_id` | `app_user.user_id` | N:1 | no |
| `forecast_run_scenario.run_id` | `forecast_run.run_id` | N:1 | no |
| `forecast_run_scenario.scenario_id` | `liquidity_scenario.scenario_id` | N:1 | no |
| `forecast_run_item.run_id` | `forecast_run.run_id` | N:1 | no |
| `forecast_run_item.cf_id` | `cash_flow_forecast.cf_id` | N:1 | no |
| `forecast_run_item.revision_id` | `cf_revision.revision_id` | N:1 | yes |
| `forecast_run_item.currency` | `currency.currency_code` | N:1 | no |
| `forecast_run_balance_input.run_id` | `forecast_run.run_id` | N:1 | no |
| `forecast_run_balance_input.account_id` | `bank_account.account_id` | N:1 | no |
| `forecast_run_balance_input.statement_id` | `bank_statement.statement_id` | N:1 | no |
| `forecast_run_balance_input.currency` | `currency.currency_code` | N:1 | no |
| `forecast_run_fx_input.run_id` | `forecast_run.run_id` | N:1 | no |
| `forecast_run_fx_input.currency_code` | `currency.currency_code` | N:1 | no |
| `forecast_run_fx_input.rate_id` | `currency_rate.rate_id` | N:1 | no |
| `forecast_position.run_id` | `forecast_run.run_id` | N:1 | no |
| `forecast_position.scenario_id` | `liquidity_scenario.scenario_id` | N:1 | no |
| `forecast_position.entity_id` | `legal_entity.entity_id` | N:1 | no |
| `daily_cash_position.account_id` | `bank_account.account_id` | N:1 | no |
| `daily_cash_position.entity_id` | `legal_entity.entity_id` | N:1 | no |
| `daily_cash_position.currency` | `currency.currency_code` | N:1 | no |
| `daily_cash_position.fx_rate_id` | `currency_rate.rate_id` | N:1 | yes |
| `entity_cash_position.entity_id` | `legal_entity.entity_id` | N:1 | no |
| `scenario_assumption_effect.run_id` | `forecast_run.run_id` | N:1 | no |
| `scenario_assumption_effect.scenario_id` | `liquidity_scenario.scenario_id` | N:1 | no |
| `scenario_assumption_effect.assumption_id` | `scenario_assumption.assumption_id` | N:1 | no |
| `forecast_vs_actual.run_id` | `forecast_run.run_id` | N:1 | no |
| `forecast_vs_actual.scenario_id` | `liquidity_scenario.scenario_id` | N:1 | no |
| `forecast_vs_actual.entity_id` | `legal_entity.entity_id` | N:1 | no |
| `variance_attribution.run_id` | `forecast_run.run_id` | N:1 | no |
| `variance_attribution.scenario_id` | `liquidity_scenario.scenario_id` | N:1 | no |
| `variance_attribution.entity_id` | `legal_entity.entity_id` | N:1 | no |
| `variance_attribution.cf_id` | `cash_flow_forecast.cf_id` | N:1 | yes |
| `variance_attribution.ledger_entry_id` | `ledger_entry.ledger_entry_id` | N:1 | yes |
| `exception.entity_id` | `legal_entity.entity_id` | N:1 | yes |
| `exception.account_id` | `bank_account.account_id` | N:1 | yes |
| `exception.run_id` | `forecast_run.run_id` | N:1 | yes |
| `exception_event.exception_id` | `exception.exception_id` | N:1 | no |
| `exception_event.actor_id` | `app_user.user_id` | N:1 | no |
| `audit_event.actor_id` | `app_user.user_id` | N:1 | no |

**Many-to-many relationships** are resolved by bridge tables:

- `scenario_assumption_link`: liquidity_scenario N:M scenario_assumption
- `settlement_allocation`: ledger_entry N:M receivable / payable
- `forecast_run_scenario`: forecast_run N:M liquidity_scenario
- `forecast_run_item`: forecast_run N:M cash_flow_forecast

## Effective dates and lifecycles

Columns that make records time-aware:

- `app_user`: `active_from`
- `currency_rate`: `rate_date`, `recorded_at`
- `liquidity_scenario`: `effective_from`, `effective_to`
- `legal_entity`: `effective_from`, `effective_to`
- `bank_account`: `opened_on`, `opening_balance_date`, `closed_on`
- `receivable`: `recorded_at`
- `payable`: `recorded_at`
- `cash_flow_forecast`: `recorded_at`
- `ledger_entry`: `recorded_at`
- `bank_statement`: `recorded_at`
- `cf_revision`: `recorded_at`
- `forecast_run`: `cutoff_date`, `knowledge_cutoff_ts`
- `forecast_run_fx_input`: `rate_date`

State machines enforced by the validator (an event must start from the current state):

### bank_account (history in `bank_account_event`)

| Event | From | To |
|---|---|---|
| `OPENED` | (new) | `ACTIVE` |
| `FROZEN` | `ACTIVE` | `FROZEN` |
| `UNFROZEN` | `FROZEN` | `ACTIVE` |
| `CLOSED` | `ACTIVE` | `CLOSED` |

Terminal states: `CLOSED`.

### receivable (history in `receivable_event`)

| Event | From | To |
|---|---|---|
| `CREATED` | (new) | `OPEN` |
| `PARTIAL_PAYMENT` | `OPEN` | `PARTIALLY_PAID` |
| `PARTIAL_PAYMENT` | `PARTIALLY_PAID` | `PARTIALLY_PAID` |
| `PARTIAL_PAYMENT` | `OVERDUE` | `PARTIALLY_PAID` |
| `OVERDUE` | `OPEN` | `OVERDUE` |
| `OVERDUE` | `PARTIALLY_PAID` | `OVERDUE` |
| `PAID` | `OPEN` | `PAID` |
| `PAID` | `PARTIALLY_PAID` | `PAID` |
| `PAID` | `OVERDUE` | `PAID` |
| `WRITTEN_OFF` | `OVERDUE` | `WRITTEN_OFF` |

Terminal states: `PAID`, `WRITTEN_OFF`.

### payable (history in `payable_event`)

| Event | From | To |
|---|---|---|
| `CREATED` | (new) | `SCHEDULED` |
| `APPROVED` | `SCHEDULED` | `APPROVED` |
| `HELD` | `SCHEDULED` | `ON_HOLD` |
| `HELD` | `APPROVED` | `ON_HOLD` |
| `RELEASED` | `ON_HOLD` | `APPROVED` |
| `PAID` | `APPROVED` | `PAID` |
| `CANCELLED` | `SCHEDULED` | `CANCELLED` |
| `CANCELLED` | `APPROVED` | `CANCELLED` |
| `CANCELLED` | `ON_HOLD` | `CANCELLED` |

Terminal states: `PAID`, `CANCELLED`.

### cash_flow_forecast (history in `cf_revision`)

| Event | From | To |
|---|---|---|
| `DATE_CHANGE` | `ACTIVE` | `ACTIVE` |
| `AMOUNT_CHANGE` | `ACTIVE` | `ACTIVE` |
| `SETTLED` | `ACTIVE` | `SETTLED` |
| `CANCELLED` | `ACTIVE` | `CANCELLED` |

Terminal states: `SETTLED`, `CANCELLED`. Items start as `ACTIVE`.

### forecast_run (history in `forecast_run_event`)

| Event | From | To |
|---|---|---|
| `CREATED` | (new) | `CREATED` |
| `COMPLETED` | `CREATED` | `COMPLETED` |
| `SUBMITTED` | `COMPLETED` | `SUBMITTED` |
| `APPROVED` | `SUBMITTED` | `APPROVED` |
| `REJECTED` | `SUBMITTED` | `REJECTED` |
| `SUPERSEDED` | `APPROVED` | `SUPERSEDED` |

Terminal states: `REJECTED`, `SUPERSEDED`.

### exception (history in `exception_event`)

| Event | From | To |
|---|---|---|
| `RAISED` | (new) | `OPEN` |
| `ASSIGNED` | `OPEN` | `ASSIGNED` |
| `ESCALATED` | `ASSIGNED` | `ESCALATED` |
| `RESOLVED` | `ASSIGNED` | `RESOLVED` |
| `RESOLVED` | `ESCALATED` | `RESOLVED` |
| `WAIVED` | `ESCALATED` | `WAIVED` |

Terminal states: `RESOLVED`, `WAIVED`.

## Columns

### currency

ISO 4217 currencies in scope. Minor units drive rounding and formatting.

Layer: **reference** · Grain: One row per currency. · Primary key: `currency_code`

| Column | Type | Required | Allowed values / format | Units | Unique | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `currency_code` | string | yes | `USD`, `EUR`, `GBP`, `INR`, `JPY` |  | yes |  |  | ISO 4217 alphabetic code |
| `currency_name` | string | yes |  |  |  |  |  | Display name |
| `minor_units` | int | yes | `0`, `2` | decimal places |  |  |  | ISO 4217 minor units (JPY has none) |
| `is_reporting_currency` | bool | yes |  |  |  |  | Exactly one row is true (USD) | Group reporting currency flag |

### app_user

Synthetic users acting in the workflow. Names are role labels, not people.

Layer: **reference** · Grain: One row per user. · Primary key: `user_id`

| Column | Type | Required | Allowed values / format | Units | Unique | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `user_id` | string | yes | pattern `^USR-\d{4}$` |  | yes |  |  | Immutable user ID |
| `display_name` | string | yes |  |  |  |  |  | Role-based label |
| `role` | string | yes | `SYSTEM`, `SYS_ADMIN`, `OPS_ANALYST`, `RISK_REVIEWER`, `ACCOUNT_HOLDER` |  |  |  |  | Workflow role; drives permissions |
| `entity_id` | string | no |  |  |  | `legal_entity.entity_id` | Required for ACCOUNT_HOLDER, null otherwise | Entity an account holder belongs to |
| `active_from` | date | yes |  |  |  |  |  | First day the user may act |

### counterparty

Fictional customers and suppliers. Customer risk tier drives payment behaviour.

Layer: **reference** · Grain: One row per counterparty. · Primary key: `counterparty_id`

| Column | Type | Required | Allowed values / format | Units | Unique | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `counterparty_id` | string | yes | pattern `^CPTY-\d{6}$` |  | yes |  |  | Immutable counterparty ID |
| `counterparty_name` | string | yes |  |  |  |  |  | Fictional company name |
| `counterparty_type` | string | yes | `CUSTOMER`, `SUPPLIER` |  |  |  |  | Trading relationship |
| `country_code` | string | yes | `US`, `DE`, `NL`, `FR`, `GB`, `IN`, `JP` |  |  |  |  | Country |
| `default_currency` | string | yes |  |  |  | `currency.currency_code` |  | Currency the counterparty prefers to trade in |
| `risk_tier` | string | yes | `A`, `B`, `C`, `D` |  |  |  |  | Credit/payment risk; A best, D worst |
| `payment_terms_days` | int | yes | `15`, `30`, `45`, `60`, `90` | days |  |  |  | Contractual payment terms |

### currency_rate

Daily closing FX rates against USD, one per business day and currency.

Layer: **reference** · Grain: One row per (rate_date, base_currency). · Primary key: `rate_id` · Unique: `(rate_date, base_currency, quote_currency)`

| Column | Type | Required | Allowed values / format | Units | Unique | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `rate_id` | string | yes | pattern `^FXR-\d{4}-\d{2}-\d{2}-[A-Z]{3}-USD$` |  | yes |  | Embeds rate_date and base_currency | Immutable rate ID |
| `rate_date` | date | yes |  |  |  |  | Business day | Fixing date |
| `base_currency` | string | yes | `EUR`, `GBP`, `INR`, `JPY` |  |  | `currency.currency_code` |  | Currency being priced |
| `quote_currency` | string | yes | `USD` |  |  | `currency.currency_code` |  | Always USD |
| `rate` | rate | yes | ≥ 0 | USD per 1 unit of base_currency |  |  |  | Closing rate |
| `rate_type` | string | yes | `CLOSING` |  |  |  |  | Rate type |
| `source` | string | yes | `SYNTHETIC_GBM` |  |  |  |  | Provenance of the rate |
| `recorded_at` | timestamp | yes |  |  |  |  | On rate_date, after the close | When the rate was loaded |

### liquidity_scenario

Versioned liquidity scenarios. A scenario is defined only by its linked assumptions.

Layer: **reference** · Grain: One row per scenario version. · Primary key: `scenario_id`

| Column | Type | Required | Allowed values / format | Units | Unique | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `scenario_id` | string | yes | pattern `^SCN-(BASE\|DELAY\|STRESS)-V\d{2}$` |  | yes |  |  | Immutable scenario version ID |
| `scenario_code` | string | yes | `BASE`, `DELAY`, `STRESS` |  |  |  |  | Scenario family |
| `version` | int | yes | ≥ 1 |  |  |  |  | Version within the family |
| `scenario_name` | string | yes |  |  |  |  |  | Display name |
| `description` | string | yes |  |  |  |  |  | What the scenario represents |
| `effective_from` | date | yes |  |  |  |  |  | First cutoff date the version applies to |
| `effective_to` | date | no |  |  |  |  | Null while current | Last cutoff date the version applies to |
| `status` | string | yes | `ACTIVE`, `RETIRED` |  |  |  |  | Status at the end of the period |
| `supersedes_scenario_id` | string | no |  |  |  | `liquidity_scenario.scenario_id` |  | Previous version of the same family |
| `created_by` | string | yes |  |  |  | `app_user.user_id` |  | System administrator who published it |
| `created_at` | timestamp | yes |  |  |  |  |  | Publication time |

### scenario_assumption

Documented, parameterised assumptions. Scenarios differ only through these rows.

Layer: **reference** · Grain: One row per assumption. · Primary key: `assumption_id`

| Column | Type | Required | Allowed values / format | Units | Unique | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `assumption_id` | string | yes | pattern `^ASM-\d{4}$` |  | yes |  |  | Immutable assumption ID |
| `parameter` | string | yes | `AR_DELAY_DAYS`, `AR_COLLECTION_RATE`, `AP_TIMING_SHIFT_DAYS`, `RUN_RATE_INFLOW_FACTOR`, `FX_SHOCK_PCT` |  |  |  |  | What the assumption changes |
| `filter_field` | string | no | `risk_tier`, `currency_not` |  |  |  |  | Which items it applies to (null = all eligible items) |
| `filter_value` | string | no |  |  |  |  |  | Filter value, e.g. C for risk_tier |
| `value` | decimal | yes |  |  |  |  |  | Parameter value |
| `unit` | string | yes | `days`, `ratio`, `pct` |  |  |  |  | Unit of value |
| `rationale` | string | yes |  |  |  |  |  | Why the assumption exists |

### scenario_assumption_link

Which assumptions make up each scenario version, in application order.

Layer: **bridge** · Grain: One row per (scenario, assumption). · Primary key: `scenario_id, assumption_id`

| Column | Type | Required | Allowed values / format | Units | Unique | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `scenario_id` | string | yes |  |  |  | `liquidity_scenario.scenario_id` |  | Scenario version |
| `assumption_id` | string | yes |  |  |  | `scenario_assumption.assumption_id` |  | Assumption |
| `apply_order` | int | yes | ≥ 1 |  |  |  |  | Order in which assumptions are applied |

### legal_entity

Companies in the group. One holding company owns every operating entity.

Layer: **master** · Grain: One row per legal entity. · Primary key: `entity_id`

| Column | Type | Required | Allowed values / format | Units | Unique | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `entity_id` | string | yes | pattern `^ENT-\d{6}$` |  | yes |  |  | Immutable entity ID |
| `entity_name` | string | yes |  |  |  |  |  | Fictional company name |
| `country_code` | string | yes | `US`, `DE`, `NL`, `FR`, `GB`, `IN`, `JP` |  |  |  |  | Country of incorporation |
| `functional_currency` | string | yes |  |  |  | `currency.currency_code` |  | Currency of the entity's books |
| `entity_type` | string | yes | `HOLDING`, `OPERATING` |  |  |  |  | Role in the group |
| `parent_entity_id` | string | no |  |  |  | `legal_entity.entity_id` | Null only for the HOLDING entity | Owning entity |
| `size_tier` | string | yes | `S`, `M`, `L` |  |  |  |  | Size band; drives volumes and liquidity buffer |
| `min_liquidity_buffer` | money (in functional_currency) | yes | ≥ 0 | functional currency |  |  |  | Minimum available cash the entity must hold |
| `effective_from` | date | yes |  |  |  |  |  | First day the entity is part of the group |
| `effective_to` | date | no |  |  |  |  | Null while the entity is in the group | Last day in the group |
| `status` | string | yes | `ACTIVE`, `INACTIVE` |  |  |  |  | Status at the end of the actuals period |

### bank_account

Bank accounts held by the entities. Pool headers concentrate cash per currency.

Layer: **master** · Grain: One row per account. · Primary key: `account_id`

| Column | Type | Required | Allowed values / format | Units | Unique | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `account_id` | string | yes | pattern `^BANKACC-ENT-\d{6}-\d{3}$` |  | yes |  | Embeds the owning entity_id | Immutable account ID |
| `entity_id` | string | yes |  |  |  | `legal_entity.entity_id` |  | Account holder |
| `bank_name` | string | yes |  |  |  |  |  | Fictional bank |
| `account_number_masked` | string | yes | pattern `^\*{4}\d{4}$` |  |  |  |  | Masked synthetic account number |
| `currency` | string | yes |  |  |  | `currency.currency_code` |  | Account currency |
| `account_type` | string | yes | `CONCENTRATION`, `OPERATING`, `COLLECTION`, `PAYROLL`, `DEPOSIT`, `RESTRICTED` |  |  |  |  | Purpose of the account |
| `is_restricted` | bool | yes |  |  |  |  | True only for RESTRICTED accounts; excluded from available liquidity | Restricted cash flag |
| `is_pool_header` | bool | yes |  |  |  |  | At most one header per currency | Cash-pool header for its currency |
| `overdraft_limit` | money (in currency) | yes | ≥ 0 |  |  |  |  | Committed overdraft |
| `opened_on` | date | yes |  |  |  |  |  | Date the account was opened at the bank |
| `opening_balance_date` | date | yes |  |  |  |  | max(opened_on, entity effective_from, start_date) | Date the opening balance applies to |
| `opening_balance` | money (in currency) | yes |  |  |  |  |  | Balance at the start of opening_balance_date |
| `closed_on` | date | no |  |  |  |  | Balance must be zero after closure | Closure date |
| `status_at_end` | string | yes | `ACTIVE`, `FROZEN`, `CLOSED` |  |  |  | Equals the last bank_account_event status | Derived status at the end of the actuals period |

### receivable

Customer invoices (accounts receivable) with expected collection dates.

Layer: **transaction** · Grain: One row per invoice. · Primary key: `receivable_id`

| Column | Type | Required | Allowed values / format | Units | Unique | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `receivable_id` | string | yes | pattern `^AR-\d{4}-\d{6}$` |  | yes |  |  | Immutable receivable ID |
| `entity_id` | string | yes |  |  |  | `legal_entity.entity_id` |  | Invoicing entity |
| `account_id` | string | yes |  |  |  | `bank_account.account_id` | Account belongs to entity_id | Collection account |
| `counterparty_id` | string | yes |  |  |  | `counterparty.counterparty_id` |  | Customer |
| `invoice_number` | string | yes | pattern `^INV-\d{6}-\d{6}$` |  | yes |  |  | Invoice number |
| `invoice_date` | date | yes |  |  |  |  |  | Invoice date |
| `due_date` | date | yes |  |  |  |  | due_date >= invoice_date | Contractual due date |
| `currency` | string | yes |  |  |  | `currency.currency_code` |  | Invoice currency |
| `amount` | money (in currency) | yes | ≥ 0 |  |  |  |  | Invoice amount |
| `recorded_at` | timestamp | yes |  |  |  |  |  | When the AR system recorded the invoice |
| `status_at_end` | string | yes | `OPEN`, `PARTIALLY_PAID`, `OVERDUE`, `PAID`, `WRITTEN_OFF` |  |  |  | Equals the last receivable_event status | Derived status at the end of the actuals period |

### payable

Supplier bills and large one-off obligations (accounts payable).

Layer: **transaction** · Grain: One row per bill. · Primary key: `payable_id`

| Column | Type | Required | Allowed values / format | Units | Unique | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `payable_id` | string | yes | pattern `^AP-\d{4}-\d{6}$` |  | yes |  |  | Immutable payable ID |
| `entity_id` | string | yes |  |  |  | `legal_entity.entity_id` |  | Paying entity |
| `account_id` | string | yes |  |  |  | `bank_account.account_id` | Account belongs to entity_id | Paying account |
| `counterparty_id` | string | yes |  |  |  | `counterparty.counterparty_id` |  | Supplier |
| `bill_number` | string | yes | pattern `^BILL-\d{6}-\d{6}$` |  | yes |  |  | Bill number |
| `bill_date` | date | yes |  |  |  |  |  | Bill date |
| `due_date` | date | yes |  |  |  |  | due_date >= bill_date | Contractual due date |
| `currency` | string | yes |  |  |  | `currency.currency_code` |  | Bill currency |
| `amount` | money (in currency) | yes | ≥ 0 |  |  |  |  | Bill amount |
| `category` | string | yes | `TRADE`, `CAPEX`, `ACQUISITION`, `DEBT_REPAYMENT`, `TAX_SETTLEMENT`, `LEGAL_SETTLEMENT` |  |  |  |  | Nature of the obligation |
| `is_one_off` | bool | yes |  |  |  |  | True for the large non-recurring payments | Large one-off payment flag |
| `recorded_at` | timestamp | yes |  |  |  |  |  | When the AP system recorded the bill |
| `status_at_end` | string | yes | `SCHEDULED`, `APPROVED`, `ON_HOLD`, `PAID`, `CANCELLED` |  |  |  | Equals the last payable_event status | Derived status at the end of the actuals period |

### cash_flow_forecast

Expected cash-flow items: subledger feeds, recurring schedules, run-rate estimates and manual submissions.

Layer: **transaction** · Grain: One row per forecast item; later changes are cf_revision rows. · Primary key: `cf_id`

| Column | Type | Required | Allowed values / format | Units | Unique | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `cf_id` | string | yes | pattern `^CF-\d{4}-\d{6}$` |  | yes |  |  | Immutable forecast item ID |
| `entity_id` | string | yes |  |  |  | `legal_entity.entity_id` |  | Entity |
| `account_id` | string | yes |  |  |  | `bank_account.account_id` | Account belongs to entity_id | Account the cash is expected on |
| `direction` | string | yes | `INFLOW`, `OUTFLOW` |  |  |  |  | Cash direction |
| `flow_category` | string | yes | `AR_COLLECTION`, `AP_PAYMENT`, `PAYROLL`, `RENT`, `TAX`, `DEBT_SERVICE`, `OPERATING_RUN_RATE`, `OTHER` |  |  |  |  | Business category |
| `source_system` | string | yes | `AR_SUBLEDGER`, `AP_SUBLEDGER`, `PAYROLL_SYSTEM`, `LEASE_SYSTEM`, `TAX_CALENDAR`, `LOAN_SYSTEM`, `RUN_RATE_MODEL`, `MANUAL` |  |  |  |  | Where the item came from |
| `receivable_id` | string | no |  |  |  | `receivable.receivable_id` | Set for AR_SUBLEDGER items | Source invoice |
| `payable_id` | string | no |  |  |  | `payable.payable_id` | Set for AP_SUBLEDGER items | Source bill |
| `counterparty_id` | string | no |  |  |  | `counterparty.counterparty_id` |  | Counterparty, when known |
| `source_reference` | string | no |  |  |  |  |  | Invoice/bill number or manual reference |
| `currency` | string | yes |  |  |  | `currency.currency_code` | Must equal the account currency unless the amount was converted | Currency of amount |
| `amount` | money (in currency) | yes | ≥ 0 |  |  |  |  | Expected amount (unsigned; sign from direction) |
| `original_currency` | string | no |  |  |  | `currency.currency_code` | Set when the source document is in another currency | Source document currency |
| `original_amount` | money (in original_currency) | no |  |  |  |  |  | Amount in the source document currency |
| `fx_rate_id` | string | no |  |  |  | `currency_rate.rate_id` | Required when original_currency is set | Rate used to convert original_amount |
| `expected_date` | date | yes |  |  |  |  |  | Expected value date when first recorded |
| `recorded_at` | timestamp | yes |  |  |  |  |  | When the item became known |
| `created_by` | string | yes |  |  |  | `app_user.user_id` |  | System feed or account holder |

### ledger_entry

Booked cash movements (actuals). Positive = inflow, negative = outflow, in account currency.

Layer: **transaction** · Grain: One row per posting. · Primary key: `ledger_entry_id`

| Column | Type | Required | Allowed values / format | Units | Unique | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `ledger_entry_id` | string | yes | pattern `^LED-\d{4}-\d{8}$` |  | yes |  | Year equals the posting year | Immutable ledger entry ID |
| `account_id` | string | yes |  |  |  | `bank_account.account_id` |  | Account |
| `entity_id` | string | yes |  |  |  | `legal_entity.entity_id` | Equals the account's entity_id | Entity (denormalised for joins) |
| `posting_date` | date | yes |  |  |  |  | Business day within the account's active period | Value/posting date |
| `recorded_at` | timestamp | yes |  |  |  |  |  | When the posting was recorded |
| `currency` | string | yes |  |  |  | `currency.currency_code` | Equals the account currency | Currency of amount |
| `amount` | money (in currency) | yes |  |  |  |  | Non-zero | Signed amount |
| `entry_type` | string | yes | `AR_RECEIPT`, `AP_PAYMENT`, `PAYROLL`, `RENT`, `TAX`, `DEBT_SERVICE`, `BANK_FEE`, `INTEREST`, `OPERATING_RECEIPT`, `OPERATING_PAYMENT`, `OTHER_RECEIPT`, `OTHER_PAYMENT`, `POOL_SWEEP`, `POOL_FUNDING`, `FX_CONVERSION`, `ACCOUNT_CLOSURE` |  |  |  |  | Economic type |
| `cf_id` | string | no |  |  |  | `cash_flow_forecast.cf_id` | Set when the posting realises a recurring or manual forecast item | Realised forecast item |
| `counterparty_id` | string | no |  |  |  | `counterparty.counterparty_id` |  | Counterparty |
| `transfer_group_id` | string | no | pattern `^TRF-\d{4}-\d{6}$` |  |  |  | Both legs of an internal transfer share it and net to zero (FX legs net at the rate) | Internal transfer group |
| `fx_rate_id` | string | no |  |  |  | `currency_rate.rate_id` |  | Rate used for FX conversions and cross-currency receipts |
| `original_currency` | string | no |  |  |  | `currency.currency_code` |  | Currency of the other side of a conversion |
| `original_amount` | money (in original_currency) | no |  |  |  |  |  | Amount in original_currency |
| `description` | string | yes |  |  |  |  |  | Narrative |

### settlement_allocation

How cash postings settle invoices and bills: one transfer may pay several invoices, one invoice may be paid in parts.

Layer: **bridge** · Grain: One row per (ledger entry, document). · Primary key: `settlement_id`

| Column | Type | Required | Allowed values / format | Units | Unique | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `settlement_id` | string | yes | pattern `^SETL-\d{4}-\d{7}$` |  | yes |  |  | Immutable allocation ID |
| `ledger_entry_id` | string | yes |  |  |  | `ledger_entry.ledger_entry_id` |  | Cash posting |
| `receivable_id` | string | no |  |  |  | `receivable.receivable_id` | Exactly one of receivable_id / payable_id is set | Settled invoice |
| `payable_id` | string | no |  |  |  | `payable.payable_id` |  | Settled bill |
| `currency` | string | yes |  |  |  | `currency.currency_code` | Equals the document currency | Currency of allocated_amount |
| `allocated_amount` | money (in currency) | yes | ≥ 0 |  |  |  |  | Amount of the document settled |
| `allocation_date` | date | yes |  |  |  |  | Equals the posting date | Settlement date |

### bank_statement

Daily statements as reported by the banks (the bank's view of each account).

Layer: **transaction** · Grain: One row per account and business day while the account is active. · Primary key: `statement_id` · Unique: `(account_id, statement_date)`

| Column | Type | Required | Allowed values / format | Units | Unique | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `statement_id` | string | yes | pattern `^STM-\d{4}-\d{7}$` |  | yes |  |  | Immutable statement ID |
| `account_id` | string | yes |  |  |  | `bank_account.account_id` |  | Account |
| `statement_date` | date | yes |  |  |  |  |  | Business day covered |
| `currency` | string | yes |  |  |  | `currency.currency_code` | Equals the account currency | Statement currency |
| `opening_balance` | money (in currency) | yes |  |  |  |  | Equals the previous statement's closing_balance | Bank opening balance |
| `total_credits` | money (in currency) | yes | ≥ 0 |  |  |  |  | Sum of credits |
| `total_debits` | money (in currency) | yes | ≥ 0 |  |  |  |  | Sum of debits |
| `closing_balance` | money (in currency) | yes |  |  |  |  | opening + credits - debits; movement should equal the ledger for that day | Bank closing balance |
| `transaction_count` | int | yes | ≥ 0 |  |  |  |  | Number of transactions |
| `recorded_at` | timestamp | yes |  |  |  |  |  | When the statement was received |

### bank_account_event

Account lifecycle history (append-only).

Layer: **event** · Grain: One row per state change. · Primary key: `event_id`

| Column | Type | Required | Allowed values / format | Units | Unique | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `event_id` | string | yes | pattern `^BAE-\d{4}-\d{6}$` |  | yes |  |  | Immutable event ID |
| `account_id` | string | yes |  |  |  | `bank_account.account_id` |  | Account |
| `event_ts` | timestamp | yes |  |  |  |  |  | When it happened |
| `event_type` | string | yes | `OPENED`, `FROZEN`, `UNFROZEN`, `CLOSED` |  |  |  |  | Transition |
| `from_status` | string | no | `ACTIVE`, `FROZEN` |  |  |  |  | Status before |
| `to_status` | string | yes | `ACTIVE`, `FROZEN`, `CLOSED` |  |  |  |  | Status after |
| `actor_id` | string | yes |  |  |  | `app_user.user_id` |  | Who did it |
| `reason` | string | no |  |  |  |  |  | Why |

### receivable_event

Invoice lifecycle history (append-only).

Layer: **event** · Grain: One row per state change. · Primary key: `event_id`

| Column | Type | Required | Allowed values / format | Units | Unique | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `event_id` | string | yes | pattern `^ARE-\d{4}-\d{7}$` |  | yes |  |  | Immutable event ID |
| `receivable_id` | string | yes |  |  |  | `receivable.receivable_id` |  | Invoice |
| `event_ts` | timestamp | yes |  |  |  |  |  | When it happened |
| `event_type` | string | yes | `CREATED`, `PARTIAL_PAYMENT`, `OVERDUE`, `PAID`, `WRITTEN_OFF` |  |  |  |  | Transition |
| `from_status` | string | no | `OPEN`, `PARTIALLY_PAID`, `OVERDUE` |  |  |  |  | Status before |
| `to_status` | string | yes | `OPEN`, `PARTIALLY_PAID`, `OVERDUE`, `PAID`, `WRITTEN_OFF` |  |  |  |  | Status after |
| `currency` | string | yes |  |  |  | `currency.currency_code` | Equals the invoice currency | Currency of amount |
| `amount` | money (in currency) | no |  |  |  |  |  | Amount paid (payment events) |
| `ledger_entry_id` | string | no |  |  |  | `ledger_entry.ledger_entry_id` | Set for payment events | Cash posting |
| `actor_id` | string | yes |  |  |  | `app_user.user_id` |  | Who did it |

### payable_event

Bill lifecycle history (append-only).

Layer: **event** · Grain: One row per state change. · Primary key: `event_id`

| Column | Type | Required | Allowed values / format | Units | Unique | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `event_id` | string | yes | pattern `^APE-\d{4}-\d{7}$` |  | yes |  |  | Immutable event ID |
| `payable_id` | string | yes |  |  |  | `payable.payable_id` |  | Bill |
| `event_ts` | timestamp | yes |  |  |  |  |  | When it happened |
| `event_type` | string | yes | `CREATED`, `APPROVED`, `HELD`, `RELEASED`, `PAID`, `CANCELLED` |  |  |  |  | Transition |
| `from_status` | string | no | `SCHEDULED`, `APPROVED`, `ON_HOLD` |  |  |  |  | Status before |
| `to_status` | string | yes | `SCHEDULED`, `APPROVED`, `ON_HOLD`, `PAID`, `CANCELLED` |  |  |  |  | Status after |
| `ledger_entry_id` | string | no |  |  |  | `ledger_entry.ledger_entry_id` | Set for PAID | Cash posting |
| `actor_id` | string | yes |  |  |  | `app_user.user_id` |  | Who did it (approvals of large bills need a risk reviewer) |

### cf_revision

Later changes to forecast items (new date, new amount, settled, cancelled). Items themselves never change.

Layer: **event** · Grain: One row per revision. · Primary key: `revision_id` · Unique: `(cf_id, revision_no)`

| Column | Type | Required | Allowed values / format | Units | Unique | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `revision_id` | string | yes | pattern `^CFR-\d{4}-\d{7}$` |  | yes |  |  | Immutable revision ID |
| `cf_id` | string | yes |  |  |  | `cash_flow_forecast.cf_id` |  | Forecast item |
| `revision_no` | int | yes | ≥ 1 |  |  |  | Consecutive per item | Sequence per item |
| `recorded_at` | timestamp | yes |  |  |  |  | After the item's recorded_at and the previous revision | When the change became known |
| `revision_type` | string | yes | `DATE_CHANGE`, `AMOUNT_CHANGE`, `SETTLED`, `CANCELLED` |  |  |  |  | Kind of change |
| `new_expected_date` | date | no |  |  |  |  | Set for DATE_CHANGE | New expected date |
| `currency` | string | yes |  |  |  | `currency.currency_code` | Equals the item currency | Currency of new_amount |
| `new_amount` | money (in currency) | no |  |  |  |  | Set for AMOUNT_CHANGE | New remaining amount |
| `reason` | string | yes | `CUSTOMER_ADVISED_DELAY`, `PARTIAL_PAYMENT`, `PAID_IN_FULL`, `WRITTEN_OFF`, `SUPPLIER_HOLD`, `HOLD_RELEASED`, `PAYMENT_DEFERRED`, `PAYMENT_CANCELLED`, `RUN_RATE_REESTIMATE`, `REALIZED`, `NOT_REALIZED` |  |  |  |  | Business reason |
| `actor_id` | string | yes |  |  |  | `app_user.user_id` |  | Who recorded it |

### forecast_run

Forecast versions. Each run is an immutable 13-week projection as of a cutoff.

Layer: **history** · Grain: One row per run (cutoff date + version). · Primary key: `run_id`

| Column | Type | Required | Allowed values / format | Units | Unique | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `run_id` | string | yes | pattern `^FCAST-\d{4}-\d{2}-\d{2}-\d{3}$` |  | yes |  | Embeds cutoff_date and version | Immutable run ID |
| `cutoff_date` | date | yes |  |  |  |  |  | As-of date; first day of the horizon |
| `knowledge_cutoff_ts` | timestamp | yes |  |  |  |  | Inputs must be recorded before this instant | Knowledge cutoff |
| `horizon_start` | date | yes |  |  |  |  | Equals cutoff_date | First projected day |
| `horizon_end` | date | yes |  |  |  |  | horizon_start + horizon_days - 1 | Last projected day |
| `horizon_days` | int | yes | ≥ 1 | days |  |  |  | Horizon length |
| `version` | int | yes | ≥ 1 |  |  |  |  | Version for this cutoff |
| `supersedes_run_id` | string | no |  |  |  | `forecast_run.run_id` |  | Earlier version this run replaces |
| `process` | string | yes | `LEGACY`, `CASHPILOT` |  |  |  | LEGACY runs pre-date CashPilot and have no data-quality gate | Process that produced the run |
| `run_purpose` | string | yes | `SCHEDULED`, `RERUN`, `REMEDIATION`, `LIVE` |  |  |  |  | Why the run exists |
| `reporting_currency` | string | yes |  |  |  | `currency.currency_code` |  | Currency of the results |
| `created_by` | string | yes |  |  |  | `app_user.user_id` |  | Preparer |
| `created_at` | timestamp | yes |  |  |  |  |  | Creation time |
| `input_hash` | string | yes | pattern `^[0-9a-f]{64}$` |  |  |  |  | SHA-256 of the run's input lineage |
| `result_hash` | string | yes | pattern `^[0-9a-f]{64}$` |  |  |  |  | SHA-256 of the run's results |
| `status_at_end` | string | yes | `CREATED`, `COMPLETED`, `SUBMITTED`, `APPROVED`, `REJECTED`, `SUPERSEDED` |  |  |  | Equals the last forecast_run_event status | Derived current status |

### forecast_run_event

Forecast run lifecycle history (append-only).

Layer: **event** · Grain: One row per state change. · Primary key: `event_id`

| Column | Type | Required | Allowed values / format | Units | Unique | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `event_id` | string | yes | pattern `^FRE-\d{4}-\d{6}$` |  | yes |  |  | Immutable event ID |
| `run_id` | string | yes |  |  |  | `forecast_run.run_id` |  | Run |
| `event_ts` | timestamp | yes |  |  |  |  |  | When it happened |
| `event_type` | string | yes | `CREATED`, `COMPLETED`, `SUBMITTED`, `APPROVED`, `REJECTED`, `SUPERSEDED` |  |  |  |  | Transition |
| `from_status` | string | no | `CREATED`, `COMPLETED`, `SUBMITTED`, `APPROVED` |  |  |  |  | Status before |
| `to_status` | string | yes | `CREATED`, `COMPLETED`, `SUBMITTED`, `APPROVED`, `REJECTED`, `SUPERSEDED` |  |  |  |  | Status after |
| `actor_id` | string | yes |  |  |  | `app_user.user_id` | Approver differs from preparer (four-eyes) | Who did it |
| `comment` | string | no |  |  |  |  |  | Reviewer or analyst comment |

### forecast_run_scenario

Scenarios evaluated in each run.

Layer: **bridge** · Grain: One row per (run, scenario). · Primary key: `run_id, scenario_id`

| Column | Type | Required | Allowed values / format | Units | Unique | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `run_id` | string | yes |  |  |  | `forecast_run.run_id` |  | Run |
| `scenario_id` | string | yes |  |  |  | `liquidity_scenario.scenario_id` | Scenario version effective on the cutoff date | Scenario version |

### forecast_run_item

Input lineage: every forecast item a run considered, the revision it used and how it was treated.

Layer: **bridge** · Grain: One row per (run, forecast item). · Primary key: `run_id, cf_id`

| Column | Type | Required | Allowed values / format | Units | Unique | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `run_id` | string | yes |  |  |  | `forecast_run.run_id` |  | Run |
| `cf_id` | string | yes |  |  |  | `cash_flow_forecast.cf_id` |  | Forecast item |
| `revision_id` | string | no |  |  |  | `cf_revision.revision_id` |  | Latest revision used (null = original item) |
| `input_recorded_at` | timestamp | yes |  |  |  |  | Must be before the run's knowledge cutoff | Latest recorded_at among the item and revision used |
| `treatment` | string | yes | `INCLUDED`, `OVERDUE_ROLLED`, `EXCLUDED_STALE`, `EXCLUDED_DUPLICATE`, `CONVERTED`, `QUARANTINED` |  |  |  |  | Decision applied to the item |
| `expected_date_used` | date | no |  |  |  |  | Null when excluded | Base-scenario date used |
| `currency` | string | yes |  |  |  | `currency.currency_code` |  | Account currency of amount_used |
| `amount_used` | money (in currency) | yes | ≥ 0 |  |  |  |  | Base-scenario amount used (0 when excluded) |

### forecast_run_balance_input

Input lineage: the bank statement each run used as an account's opening balance.

Layer: **history** · Grain: One row per (run, account). · Primary key: `run_id, account_id`

| Column | Type | Required | Allowed values / format | Units | Unique | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `run_id` | string | yes |  |  |  | `forecast_run.run_id` |  | Run |
| `account_id` | string | yes |  |  |  | `bank_account.account_id` |  | Account |
| `statement_id` | string | yes |  |  |  | `bank_statement.statement_id` |  | Statement used |
| `statement_date` | date | yes |  |  |  |  | Must be before the cutoff date | Statement date |
| `currency` | string | yes |  |  |  | `currency.currency_code` |  | Account currency |
| `balance_used` | money (in currency) | yes |  |  |  |  |  | Opening balance used |

### forecast_run_fx_input

Input lineage: the FX rate each run used per currency.

Layer: **history** · Grain: One row per (run, currency). · Primary key: `run_id, currency_code`

| Column | Type | Required | Allowed values / format | Units | Unique | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `run_id` | string | yes |  |  |  | `forecast_run.run_id` |  | Run |
| `currency_code` | string | yes |  |  |  | `currency.currency_code` |  | Currency converted |
| `rate_id` | string | yes |  |  |  | `currency_rate.rate_id` |  | Rate used |
| `rate_date` | date | yes |  |  |  |  | Must be before the cutoff date | Rate date |
| `rate_used` | rate | yes | ≥ 0 | USD per unit |  |  |  | Rate value |

### forecast_position

Run results: projected daily available cash per entity and scenario, in USD.

Layer: **history** · Grain: One row per (run, scenario, entity, day). · Primary key: `run_id, scenario_id, entity_id, position_date`

| Column | Type | Required | Allowed values / format | Units | Unique | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `run_id` | string | yes |  |  |  | `forecast_run.run_id` |  | Run |
| `scenario_id` | string | yes |  |  |  | `liquidity_scenario.scenario_id` |  | Scenario version |
| `entity_id` | string | yes |  |  |  | `legal_entity.entity_id` |  | Entity |
| `position_date` | date | yes |  |  |  |  | Within the run horizon | Projected day |
| `opening_available_usd` | money (USD) | yes |  |  |  |  |  | Available cash at start of day |
| `inflows_usd` | money (USD) | yes | ≥ 0 |  |  |  |  | Projected inflows |
| `outflows_usd` | money (USD) | yes | ≥ 0 |  |  |  |  | Projected outflows |
| `closing_available_usd` | money (USD) | yes |  |  |  |  | opening + inflows - outflows | Available cash at end of day |
| `restricted_usd` | money (USD) | yes | ≥ 0 |  |  |  |  | Restricted cash (excluded from available) |
| `min_buffer_usd` | money (USD) | yes | ≥ 0 |  |  |  |  | Entity liquidity buffer in USD |
| `breach_flag` | bool | yes |  |  |  |  | closing_available_usd < min_buffer_usd | Buffer breach |

### daily_cash_position

Actual daily position per account from the ledger, with the bank's view and USD value.

Layer: **derived** · Grain: One row per account and calendar day while active. · Primary key: `account_id, position_date`

| Column | Type | Required | Allowed values / format | Units | Unique | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `account_id` | string | yes |  |  |  | `bank_account.account_id` |  | Account |
| `position_date` | date | yes |  |  |  |  |  | Day |
| `entity_id` | string | yes |  |  |  | `legal_entity.entity_id` |  | Entity |
| `currency` | string | yes |  |  |  | `currency.currency_code` |  | Account currency |
| `opening_balance` | money (in currency) | yes |  |  |  |  | Previous day's closing_balance | Book opening balance |
| `inflows` | money (in currency) | yes | ≥ 0 |  |  |  |  | Sum of positive postings |
| `outflows` | money (in currency) | yes | ≥ 0 |  |  |  |  | Sum of negative postings (absolute) |
| `closing_balance` | money (in currency) | yes |  |  |  |  | opening + inflows - outflows | Book closing balance |
| `statement_closing` | money (in currency) | no |  |  |  |  |  | Bank closing balance (business days) |
| `bank_minus_book` | money (in currency) | no |  |  |  |  | Zero unless a reconciliation break is open | Unreconciled difference |
| `fx_rate_id` | string | no |  |  |  | `currency_rate.rate_id` |  | Rate used for the USD value |
| `fx_status` | string | yes | `NOT_REQUIRED`, `OK`, `FALLBACK`, `MISSING` |  |  |  |  | Quality of the rate used |
| `closing_balance_usd` | money (USD) | no |  |  |  |  | Null when fx_status is MISSING | Closing balance in USD |

### entity_cash_position

Consolidated actual daily cash per entity in USD.

Layer: **derived** · Grain: One row per entity and calendar day. · Primary key: `entity_id, position_date`

| Column | Type | Required | Allowed values / format | Units | Unique | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `entity_id` | string | yes |  |  |  | `legal_entity.entity_id` |  | Entity |
| `position_date` | date | yes |  |  |  |  |  | Day |
| `total_usd` | money (USD) | yes |  |  |  |  | Sum of account closing_balance_usd | Total cash |
| `available_usd` | money (USD) | yes |  |  |  |  | total - restricted | Available cash |
| `restricted_usd` | money (USD) | yes | ≥ 0 |  |  |  |  | Restricted cash |
| `min_buffer_usd` | money (USD) | yes | ≥ 0 |  |  |  |  | Liquidity buffer in USD |
| `headroom_usd` | money (USD) | yes |  |  |  |  | available - buffer | Headroom over buffer |
| `fx_status` | string | yes | `OK`, `FALLBACK`, `INCOMPLETE` |  |  |  |  | Worst rate quality used |
| `accounts_active` | int | yes | ≥ 0 |  |  |  |  | Accounts included |

### scenario_assumption_effect

Contribution of each assumption to a scenario, applied in order (proves scenarios differ only by documented assumptions).

Layer: **derived** · Grain: One row per (run, scenario, assumption). · Primary key: `run_id, scenario_id, assumption_id`

| Column | Type | Required | Allowed values / format | Units | Unique | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `run_id` | string | yes |  |  |  | `forecast_run.run_id` |  | Run |
| `scenario_id` | string | yes |  |  |  | `liquidity_scenario.scenario_id` |  | Scenario |
| `assumption_id` | string | yes |  |  |  | `scenario_assumption.assumption_id` |  | Assumption |
| `apply_order` | int | yes | ≥ 1 |  |  |  |  | Order applied |
| `items_affected` | int | yes | ≥ 0 |  |  |  |  | Items changed by this assumption (all match its filter) |
| `delta_net_flow_usd` | money (USD) | yes |  |  |  |  |  | Change in horizon net flow, group level |
| `delta_min_available_usd` | money (USD) | yes |  |  |  |  |  | Change in the group's lowest projected available cash |

### forecast_vs_actual

Actual-versus-forecast per run, scenario, entity and week, with the variance split into drivers.

Layer: **derived** · Grain: One row per (run, scenario, entity, week) fully inside the actuals period. · Primary key: `run_id, scenario_id, entity_id, week_no`

| Column | Type | Required | Allowed values / format | Units | Unique | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `run_id` | string | yes |  |  |  | `forecast_run.run_id` |  | Run |
| `scenario_id` | string | yes |  |  |  | `liquidity_scenario.scenario_id` |  | Scenario |
| `entity_id` | string | yes |  |  |  | `legal_entity.entity_id` |  | Entity |
| `week_no` | int | yes | ≥ 1 |  |  |  |  | Week of the horizon (1-13) |
| `week_start` | date | yes |  |  |  |  |  | First day |
| `week_end` | date | yes |  |  |  |  |  | Last day |
| `forecast_net_usd` | money (USD) | yes |  |  |  |  |  | Forecast net external flow |
| `actual_net_usd` | money (USD) | yes |  |  |  |  |  | Actual net external flow |
| `variance_usd` | money (USD) | yes |  |  |  |  | actual - forecast | Variance |
| `timing_usd` | money (USD) | yes |  |  |  |  |  | Known items realised in another week |
| `amount_usd` | money (USD) | yes |  |  |  |  |  | Known items realised at a different amount |
| `fx_usd` | money (USD) | yes |  |  |  |  |  | Rate at realisation vs rate at cutoff |
| `new_after_cutoff_usd` | money (USD) | yes |  |  |  |  |  | Items that became known after the cutoff |
| `unforecasted_usd` | money (USD) | yes |  |  |  |  |  | Cash never forecast (fees, interest) |
| `not_realized_usd` | money (USD) | yes |  |  |  |  |  | Forecast items that never happened in the horizon |
| `run_rate_usd` | money (USD) | yes |  |  |  |  |  | Small operating flows vs run-rate estimate |
| `data_quality_usd` | money (USD) | yes |  |  |  |  |  | Effect of items flagged by data-quality rules |
| `residual_usd` | money (USD) | yes |  |  |  |  | variance - sum(drivers); always 0 | Unexplained remainder |

### variance_attribution

Item-level drill-down of the base-scenario variance.

Layer: **derived** · Grain: One row per (run, entity, week, driver, record). · Primary key: `attribution_id`

| Column | Type | Required | Allowed values / format | Units | Unique | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `attribution_id` | string | yes | pattern `^VA-\d{9}$` |  | yes |  |  | Row ID |
| `run_id` | string | yes |  |  |  | `forecast_run.run_id` |  | Run |
| `scenario_id` | string | yes |  |  |  | `liquidity_scenario.scenario_id` |  | Scenario |
| `entity_id` | string | yes |  |  |  | `legal_entity.entity_id` |  | Entity |
| `week_no` | int | yes | ≥ 1 |  |  |  |  | Week |
| `driver` | string | yes | `TIMING`, `AMOUNT`, `FX`, `NEW_AFTER_CUTOFF`, `UNFORECASTED`, `NOT_REALIZED`, `RUN_RATE`, `DATA_QUALITY` |  |  |  |  | Variance driver |
| `cf_id` | string | no |  |  |  | `cash_flow_forecast.cf_id` |  | Forecast item involved |
| `ledger_entry_id` | string | no |  |  |  | `ledger_entry.ledger_entry_id` |  | Actual posting involved |
| `amount_usd` | money (USD) | yes |  |  |  |  |  | Contribution to variance |

### exception

Exceptions raised by CashPilot rules, each with a rule ID and a decision.

Layer: **output** · Grain: One row per (rule, record). · Primary key: `exception_id`

| Column | Type | Required | Allowed values / format | Units | Unique | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `exception_id` | string | yes | pattern `^EXC-\d{4}-\d{6}$` |  | yes |  |  | Immutable exception ID |
| `rule_id` | string | yes | pattern `^R-[A-Z]+-\d{3}$` |  |  |  |  | Rule that fired (docs/RULES.md) |
| `category` | string | yes | `DATA_QUALITY`, `BUSINESS_ALERT` |  |  |  |  | Data problem or business alert |
| `exception_type` | string | yes | `BALANCE_BREAK`, `FX_RATE_MISSING`, `DUPLICATE_CASH_FLOW`, `LOOKAHEAD_LEAKAGE`, `MIXED_CURRENCY`, `LIQUIDITY_BREACH` |  |  |  |  | Type |
| `severity` | string | yes | `LOW`, `MEDIUM`, `HIGH`, `CRITICAL` |  |  |  |  | Severity by rule |
| `record_table` | string | yes |  |  |  |  |  | Table of the flagged record |
| `record_id` | string | yes |  |  |  |  |  | Flagged record |
| `related_record_id` | string | no |  |  |  |  |  | Other record involved (e.g. the original of a duplicate) |
| `entity_id` | string | no |  |  |  | `legal_entity.entity_id` |  | Entity |
| `account_id` | string | no |  |  |  | `bank_account.account_id` |  | Account |
| `run_id` | string | no |  |  |  | `forecast_run.run_id` |  | Run |
| `impact_usd` | money (USD) | no |  |  |  |  |  | Estimated impact |
| `decision` | string | yes | `RAISE_RECON_BREAK`, `USE_PREVIOUS_RATE`, `BLOCK_CONVERSION`, `EXCLUDE_DUPLICATE`, `CONVERT_AT_CUTOFF_RATE`, `QUARANTINE_ITEM`, `SUPERSEDE_WITH_RERUN`, `FUNDING_REVIEW` |  |  |  |  | Decision applied by rule |
| `details` | string | yes |  |  |  |  |  | Human-readable explanation |
| `detected_at` | timestamp | yes |  |  |  |  |  | Detection time |
| `status_at_end` | string | yes | `OPEN`, `ASSIGNED`, `ESCALATED`, `RESOLVED`, `WAIVED` |  |  |  | Equals the last exception_event status | Derived current status |

### exception_event

Exception workflow history (append-only).

Layer: **output** · Grain: One row per state change. · Primary key: `event_id`

| Column | Type | Required | Allowed values / format | Units | Unique | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `event_id` | string | yes | pattern `^EXE-\d{4}-\d{6}$` |  | yes |  |  | Immutable event ID |
| `exception_id` | string | yes |  |  |  | `exception.exception_id` |  | Exception |
| `event_ts` | timestamp | yes |  |  |  |  |  | When it happened |
| `event_type` | string | yes | `RAISED`, `ASSIGNED`, `ESCALATED`, `RESOLVED`, `WAIVED` |  |  |  |  | Transition |
| `from_status` | string | no | `OPEN`, `ASSIGNED`, `ESCALATED` |  |  |  |  | Status before |
| `to_status` | string | yes | `OPEN`, `ASSIGNED`, `ESCALATED`, `RESOLVED`, `WAIVED` |  |  |  |  | Status after |
| `actor_id` | string | yes |  |  |  | `app_user.user_id` | Waivers need a risk reviewer | Who did it |
| `comment` | string | no |  |  |  |  |  | Justification or resolution note |

### audit_event

Every workflow action attempted through CashPilot, allowed or denied.

Layer: **output** · Grain: One row per attempted action. · Primary key: `event_id`

| Column | Type | Required | Allowed values / format | Units | Unique | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `event_id` | string | yes | pattern `^AUD-\d{4}-\d{6}$` |  | yes |  |  | Immutable audit ID |
| `event_ts` | timestamp | yes |  |  |  |  |  | When |
| `actor_id` | string | yes |  |  |  | `app_user.user_id` |  | Who |
| `action` | string | yes | `VIEW_ENTITY`, `CREATE_RUN`, `SUBMIT_RUN`, `APPROVE_RUN`, `REJECT_RUN`, `SUPERSEDE_RUN`, `ASSIGN_EXCEPTION`, `ESCALATE_EXCEPTION`, `RESOLVE_EXCEPTION`, `WAIVE_EXCEPTION` |  |  |  |  | Action |
| `target_id` | string | yes |  |  |  |  |  | Record acted on |
| `outcome` | string | yes | `ALLOWED`, `DENIED` |  |  |  |  | Result of the permission check |
| `detail` | string | no |  |  |  |  |  | Reason when denied |

### anomaly_label

Ground truth for injected anomalies and legitimate look-alikes. Stored separately; never read by detectors.

Layer: **ground_truth** · Grain: One row per labelled record. · Primary key: `gt_id`

| Column | Type | Required | Allowed values / format | Units | Unique | References | Validation rule | Description |
|---|---|---|---|---|---|---|---|---|
| `gt_id` | string | yes | pattern `^GT-\d{6}$` |  | yes |  |  | Label ID |
| `label` | string | yes | `ANOMALY`, `NEGATIVE_CONTROL` |  |  |  |  | Anomaly, or legitimate look-alike that must not be flagged |
| `issue_type` | string | yes | `BALANCE_BREAK`, `FX_RATE_MISSING`, `DUPLICATE_CASH_FLOW`, `LOOKAHEAD_LEAKAGE`, `MIXED_CURRENCY`, `NO_ISSUE` |  |  |  |  | Edge case |
| `sub_type` | string | yes |  |  |  |  |  | Variant of the edge case |
| `record_table` | string | yes |  |  |  |  |  | Table of the labelled record |
| `record_id` | string | yes |  |  |  |  |  | Labelled record |
| `related_record_id` | string | no |  |  |  |  |  | Other record involved |
| `field` | string | no |  |  |  |  |  | Field changed by the injection |
| `original_value` | string | no |  |  |  |  |  | Value before injection |
| `injected_value` | string | no |  |  |  |  |  | Value after injection |
| `injection_rule` | string | yes |  |  |  |  |  | Documented rule that produced the label |
| `expected_rule_id` | string | no |  |  |  |  |  | Rule expected to detect it |
| `expected_decision` | string | no |  |  |  |  |  | Decision expected from CashPilot |
| `notes` | string | no |  |  |  |  |  | Context |
