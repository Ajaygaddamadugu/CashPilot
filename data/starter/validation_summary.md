# Validation summary — `starter` dataset

**Overall: PASS** — 312 checks; a check is PASS when it finds nothing, EXPECTED when everything it finds is a labelled anomaly from the ground truth, FAIL otherwise.

**Clean baseline (before anomaly injection): 190 checks, 0 violations.** The generator produces valid data; every finding below comes from a labelled injection.

| Category | PASS | EXPECTED | FAIL |
|---|---|---|---|
| STRUCTURE | 170 | 0 | 0 |
| INTEGRITY | 80 | 0 | 0 |
| DATES | 9 | 0 | 0 |
| ARITHMETIC | 11 | 0 | 0 |
| LIFECYCLE | 11 | 0 | 0 |
| DUPLICATES | 20 | 0 | 0 |
| ANOMALY | 0 | 5 | 0 |
| VOLUME | 6 | 0 | 0 |

## Checks that found something

| Check | Description | Rows | Found | Labelled | Status | Sample |
|---|---|---|---|---|---|---|
| `R-RECON-001` | bank movement equals the booked ledger movement (opening + ledger = closing) | 4,367 | 6 | 6 | EXPECTED | STM-2026-0001198, STM-2026-0001962, STM-2026-0002295 |
| `R-FX-001` | a fixing exists for every business day | 972 | 12 | 12 | EXPECTED | FXR-2026-03-03-JPY-USD, FXR-2026-03-04-JPY-USD, FXR-2026-03-18-GBP-USD |
| `R-DUP` | no cash flow forecast twice | 2,000 | 10 | 10 | EXPECTED | CF-2026-001991, CF-2026-001992, CF-2026-001993 |
| `R-CUR` | no currency mixed without conversion | 2,000 | 6 | 6 | EXPECTED | CF-2026-000782, CF-2026-000829, CF-2026-001185 |
| `R-LEAK-001` | runs only use records known before their cutoff | 23 | 1 | 1 | EXPECTED | FCAST-2026-05-21-001 |

## All checks

| Check | Category | Target | Description | Rows | Status |
|---|---|---|---|---|---|
| `S-PK-currency` | STRUCTURE | currency | primary key unique and not null | 5 | PASS |
| `S-REQ-currency` | STRUCTURE | currency | required fields present | 5 | PASS |
| `S-ENUM-currency` | STRUCTURE | currency | values within allowed sets | 5 | PASS |
| `S-PAT-currency` | STRUCTURE | currency | IDs match their documented patterns | 5 | PASS |
| `S-MIN-currency` | STRUCTURE | currency | numeric minimums respected | 5 | PASS |
| `S-PK-app_user` | STRUCTURE | app_user | primary key unique and not null | 11 | PASS |
| `S-REQ-app_user` | STRUCTURE | app_user | required fields present | 11 | PASS |
| `S-ENUM-app_user` | STRUCTURE | app_user | values within allowed sets | 11 | PASS |
| `S-PAT-app_user` | STRUCTURE | app_user | IDs match their documented patterns | 11 | PASS |
| `S-MIN-app_user` | STRUCTURE | app_user | numeric minimums respected | 11 | PASS |
| `S-PK-counterparty` | STRUCTURE | counterparty | primary key unique and not null | 130 | PASS |
| `S-REQ-counterparty` | STRUCTURE | counterparty | required fields present | 130 | PASS |
| `S-ENUM-counterparty` | STRUCTURE | counterparty | values within allowed sets | 130 | PASS |
| `S-PAT-counterparty` | STRUCTURE | counterparty | IDs match their documented patterns | 130 | PASS |
| `S-MIN-counterparty` | STRUCTURE | counterparty | numeric minimums respected | 130 | PASS |
| `S-PK-currency_rate` | STRUCTURE | currency_rate | primary key unique and not null | 972 | PASS |
| `S-REQ-currency_rate` | STRUCTURE | currency_rate | required fields present | 972 | PASS |
| `S-ENUM-currency_rate` | STRUCTURE | currency_rate | values within allowed sets | 972 | PASS |
| `S-PAT-currency_rate` | STRUCTURE | currency_rate | IDs match their documented patterns | 972 | PASS |
| `S-MIN-currency_rate` | STRUCTURE | currency_rate | numeric minimums respected | 972 | PASS |
| `S-PK-liquidity_scenario` | STRUCTURE | liquidity_scenario | primary key unique and not null | 4 | PASS |
| `S-REQ-liquidity_scenario` | STRUCTURE | liquidity_scenario | required fields present | 4 | PASS |
| `S-ENUM-liquidity_scenario` | STRUCTURE | liquidity_scenario | values within allowed sets | 4 | PASS |
| `S-PAT-liquidity_scenario` | STRUCTURE | liquidity_scenario | IDs match their documented patterns | 4 | PASS |
| `S-MIN-liquidity_scenario` | STRUCTURE | liquidity_scenario | numeric minimums respected | 4 | PASS |
| `S-PK-scenario_assumption` | STRUCTURE | scenario_assumption | primary key unique and not null | 10 | PASS |
| `S-REQ-scenario_assumption` | STRUCTURE | scenario_assumption | required fields present | 10 | PASS |
| `S-ENUM-scenario_assumption` | STRUCTURE | scenario_assumption | values within allowed sets | 10 | PASS |
| `S-PAT-scenario_assumption` | STRUCTURE | scenario_assumption | IDs match their documented patterns | 10 | PASS |
| `S-MIN-scenario_assumption` | STRUCTURE | scenario_assumption | numeric minimums respected | 10 | PASS |
| `S-PK-scenario_assumption_link` | STRUCTURE | scenario_assumption_link | primary key unique and not null | 22 | PASS |
| `S-REQ-scenario_assumption_link` | STRUCTURE | scenario_assumption_link | required fields present | 22 | PASS |
| `S-ENUM-scenario_assumption_link` | STRUCTURE | scenario_assumption_link | values within allowed sets | 22 | PASS |
| `S-PAT-scenario_assumption_link` | STRUCTURE | scenario_assumption_link | IDs match their documented patterns | 22 | PASS |
| `S-MIN-scenario_assumption_link` | STRUCTURE | scenario_assumption_link | numeric minimums respected | 22 | PASS |
| `S-PK-legal_entity` | STRUCTURE | legal_entity | primary key unique and not null | 5 | PASS |
| `S-REQ-legal_entity` | STRUCTURE | legal_entity | required fields present | 5 | PASS |
| `S-ENUM-legal_entity` | STRUCTURE | legal_entity | values within allowed sets | 5 | PASS |
| `S-PAT-legal_entity` | STRUCTURE | legal_entity | IDs match their documented patterns | 5 | PASS |
| `S-MIN-legal_entity` | STRUCTURE | legal_entity | numeric minimums respected | 5 | PASS |
| `S-PK-bank_account` | STRUCTURE | bank_account | primary key unique and not null | 25 | PASS |
| `S-REQ-bank_account` | STRUCTURE | bank_account | required fields present | 25 | PASS |
| `S-ENUM-bank_account` | STRUCTURE | bank_account | values within allowed sets | 25 | PASS |
| `S-PAT-bank_account` | STRUCTURE | bank_account | IDs match their documented patterns | 25 | PASS |
| `S-MIN-bank_account` | STRUCTURE | bank_account | numeric minimums respected | 25 | PASS |
| `S-PK-receivable` | STRUCTURE | receivable | primary key unique and not null | 727 | PASS |
| `S-REQ-receivable` | STRUCTURE | receivable | required fields present | 727 | PASS |
| `S-ENUM-receivable` | STRUCTURE | receivable | values within allowed sets | 727 | PASS |
| `S-PAT-receivable` | STRUCTURE | receivable | IDs match their documented patterns | 727 | PASS |
| `S-MIN-receivable` | STRUCTURE | receivable | numeric minimums respected | 727 | PASS |
| `S-PK-payable` | STRUCTURE | payable | primary key unique and not null | 594 | PASS |
| `S-REQ-payable` | STRUCTURE | payable | required fields present | 594 | PASS |
| `S-ENUM-payable` | STRUCTURE | payable | values within allowed sets | 594 | PASS |
| `S-PAT-payable` | STRUCTURE | payable | IDs match their documented patterns | 594 | PASS |
| `S-MIN-payable` | STRUCTURE | payable | numeric minimums respected | 594 | PASS |
| `S-PK-cash_flow_forecast` | STRUCTURE | cash_flow_forecast | primary key unique and not null | 2,000 | PASS |
| `S-REQ-cash_flow_forecast` | STRUCTURE | cash_flow_forecast | required fields present | 2,000 | PASS |
| `S-ENUM-cash_flow_forecast` | STRUCTURE | cash_flow_forecast | values within allowed sets | 2,000 | PASS |
| `S-PAT-cash_flow_forecast` | STRUCTURE | cash_flow_forecast | IDs match their documented patterns | 2,000 | PASS |
| `S-MIN-cash_flow_forecast` | STRUCTURE | cash_flow_forecast | numeric minimums respected | 2,000 | PASS |
| `S-PK-ledger_entry` | STRUCTURE | ledger_entry | primary key unique and not null | 10,000 | PASS |
| `S-REQ-ledger_entry` | STRUCTURE | ledger_entry | required fields present | 10,000 | PASS |
| `S-ENUM-ledger_entry` | STRUCTURE | ledger_entry | values within allowed sets | 10,000 | PASS |
| `S-PAT-ledger_entry` | STRUCTURE | ledger_entry | IDs match their documented patterns | 10,000 | PASS |
| `S-MIN-ledger_entry` | STRUCTURE | ledger_entry | numeric minimums respected | 10,000 | PASS |
| `S-PK-settlement_allocation` | STRUCTURE | settlement_allocation | primary key unique and not null | 1,118 | PASS |
| `S-REQ-settlement_allocation` | STRUCTURE | settlement_allocation | required fields present | 1,118 | PASS |
| `S-ENUM-settlement_allocation` | STRUCTURE | settlement_allocation | values within allowed sets | 1,118 | PASS |
| `S-PAT-settlement_allocation` | STRUCTURE | settlement_allocation | IDs match their documented patterns | 1,118 | PASS |
| `S-MIN-settlement_allocation` | STRUCTURE | settlement_allocation | numeric minimums respected | 1,118 | PASS |
| `S-PK-bank_statement` | STRUCTURE | bank_statement | primary key unique and not null | 4,367 | PASS |
| `S-REQ-bank_statement` | STRUCTURE | bank_statement | required fields present | 4,367 | PASS |
| `S-ENUM-bank_statement` | STRUCTURE | bank_statement | values within allowed sets | 4,367 | PASS |
| `S-PAT-bank_statement` | STRUCTURE | bank_statement | IDs match their documented patterns | 4,367 | PASS |
| `S-MIN-bank_statement` | STRUCTURE | bank_statement | numeric minimums respected | 4,367 | PASS |
| `S-PK-bank_account_event` | STRUCTURE | bank_account_event | primary key unique and not null | 28 | PASS |
| `S-REQ-bank_account_event` | STRUCTURE | bank_account_event | required fields present | 28 | PASS |
| `S-ENUM-bank_account_event` | STRUCTURE | bank_account_event | values within allowed sets | 28 | PASS |
| `S-PAT-bank_account_event` | STRUCTURE | bank_account_event | IDs match their documented patterns | 28 | PASS |
| `S-MIN-bank_account_event` | STRUCTURE | bank_account_event | numeric minimums respected | 28 | PASS |
| `S-PK-receivable_event` | STRUCTURE | receivable_event | primary key unique and not null | 1,393 | PASS |
| `S-REQ-receivable_event` | STRUCTURE | receivable_event | required fields present | 1,393 | PASS |
| `S-ENUM-receivable_event` | STRUCTURE | receivable_event | values within allowed sets | 1,393 | PASS |
| `S-PAT-receivable_event` | STRUCTURE | receivable_event | IDs match their documented patterns | 1,393 | PASS |
| `S-MIN-receivable_event` | STRUCTURE | receivable_event | numeric minimums respected | 1,393 | PASS |
| `S-PK-payable_event` | STRUCTURE | payable_event | primary key unique and not null | 1,735 | PASS |
| `S-REQ-payable_event` | STRUCTURE | payable_event | required fields present | 1,735 | PASS |
| `S-ENUM-payable_event` | STRUCTURE | payable_event | values within allowed sets | 1,735 | PASS |
| `S-PAT-payable_event` | STRUCTURE | payable_event | IDs match their documented patterns | 1,735 | PASS |
| `S-MIN-payable_event` | STRUCTURE | payable_event | numeric minimums respected | 1,735 | PASS |
| `S-PK-cf_revision` | STRUCTURE | cf_revision | primary key unique and not null | 2,398 | PASS |
| `S-REQ-cf_revision` | STRUCTURE | cf_revision | required fields present | 2,398 | PASS |
| `S-ENUM-cf_revision` | STRUCTURE | cf_revision | values within allowed sets | 2,398 | PASS |
| `S-PAT-cf_revision` | STRUCTURE | cf_revision | IDs match their documented patterns | 2,398 | PASS |
| `S-MIN-cf_revision` | STRUCTURE | cf_revision | numeric minimums respected | 2,398 | PASS |
| `S-PK-forecast_run` | STRUCTURE | forecast_run | primary key unique and not null | 23 | PASS |
| `S-REQ-forecast_run` | STRUCTURE | forecast_run | required fields present | 23 | PASS |
| `S-ENUM-forecast_run` | STRUCTURE | forecast_run | values within allowed sets | 23 | PASS |
| `S-PAT-forecast_run` | STRUCTURE | forecast_run | IDs match their documented patterns | 23 | PASS |
| `S-MIN-forecast_run` | STRUCTURE | forecast_run | numeric minimums respected | 23 | PASS |
| `S-PK-forecast_run_scenario` | STRUCTURE | forecast_run_scenario | primary key unique and not null | 68 | PASS |
| `S-REQ-forecast_run_scenario` | STRUCTURE | forecast_run_scenario | required fields present | 68 | PASS |
| `S-ENUM-forecast_run_scenario` | STRUCTURE | forecast_run_scenario | values within allowed sets | 68 | PASS |
| `S-PAT-forecast_run_scenario` | STRUCTURE | forecast_run_scenario | IDs match their documented patterns | 68 | PASS |
| `S-MIN-forecast_run_scenario` | STRUCTURE | forecast_run_scenario | numeric minimums respected | 68 | PASS |
| `S-PK-forecast_run_item` | STRUCTURE | forecast_run_item | primary key unique and not null | 8,708 | PASS |
| `S-REQ-forecast_run_item` | STRUCTURE | forecast_run_item | required fields present | 8,708 | PASS |
| `S-ENUM-forecast_run_item` | STRUCTURE | forecast_run_item | values within allowed sets | 8,708 | PASS |
| `S-PAT-forecast_run_item` | STRUCTURE | forecast_run_item | IDs match their documented patterns | 8,708 | PASS |
| `S-MIN-forecast_run_item` | STRUCTURE | forecast_run_item | numeric minimums respected | 8,708 | PASS |
| `S-PK-forecast_run_balance_input` | STRUCTURE | forecast_run_balance_input | primary key unique and not null | 518 | PASS |
| `S-REQ-forecast_run_balance_input` | STRUCTURE | forecast_run_balance_input | required fields present | 518 | PASS |
| `S-ENUM-forecast_run_balance_input` | STRUCTURE | forecast_run_balance_input | values within allowed sets | 518 | PASS |
| `S-PAT-forecast_run_balance_input` | STRUCTURE | forecast_run_balance_input | IDs match their documented patterns | 518 | PASS |
| `S-MIN-forecast_run_balance_input` | STRUCTURE | forecast_run_balance_input | numeric minimums respected | 518 | PASS |
| `S-PK-forecast_run_fx_input` | STRUCTURE | forecast_run_fx_input | primary key unique and not null | 92 | PASS |
| `S-REQ-forecast_run_fx_input` | STRUCTURE | forecast_run_fx_input | required fields present | 92 | PASS |
| `S-ENUM-forecast_run_fx_input` | STRUCTURE | forecast_run_fx_input | values within allowed sets | 92 | PASS |
| `S-PAT-forecast_run_fx_input` | STRUCTURE | forecast_run_fx_input | IDs match their documented patterns | 92 | PASS |
| `S-MIN-forecast_run_fx_input` | STRUCTURE | forecast_run_fx_input | numeric minimums respected | 92 | PASS |
| `S-PK-forecast_position` | STRUCTURE | forecast_position | primary key unique and not null | 29,029 | PASS |
| `S-REQ-forecast_position` | STRUCTURE | forecast_position | required fields present | 29,029 | PASS |
| `S-ENUM-forecast_position` | STRUCTURE | forecast_position | values within allowed sets | 29,029 | PASS |
| `S-PAT-forecast_position` | STRUCTURE | forecast_position | IDs match their documented patterns | 29,029 | PASS |
| `S-MIN-forecast_position` | STRUCTURE | forecast_position | numeric minimums respected | 29,029 | PASS |
| `S-PK-scenario_assumption_effect` | STRUCTURE | scenario_assumption_effect | primary key unique and not null | 290 | PASS |
| `S-REQ-scenario_assumption_effect` | STRUCTURE | scenario_assumption_effect | required fields present | 290 | PASS |
| `S-ENUM-scenario_assumption_effect` | STRUCTURE | scenario_assumption_effect | values within allowed sets | 290 | PASS |
| `S-PAT-scenario_assumption_effect` | STRUCTURE | scenario_assumption_effect | IDs match their documented patterns | 290 | PASS |
| `S-MIN-scenario_assumption_effect` | STRUCTURE | scenario_assumption_effect | numeric minimums respected | 290 | PASS |
| `S-PK-forecast_run_event` | STRUCTURE | forecast_run_event | primary key unique and not null | 93 | PASS |
| `S-REQ-forecast_run_event` | STRUCTURE | forecast_run_event | required fields present | 93 | PASS |
| `S-ENUM-forecast_run_event` | STRUCTURE | forecast_run_event | values within allowed sets | 93 | PASS |
| `S-PAT-forecast_run_event` | STRUCTURE | forecast_run_event | IDs match their documented patterns | 93 | PASS |
| `S-MIN-forecast_run_event` | STRUCTURE | forecast_run_event | numeric minimums respected | 93 | PASS |
| `S-PK-daily_cash_position` | STRUCTURE | daily_cash_position | primary key unique and not null | 6,101 | PASS |
| `S-REQ-daily_cash_position` | STRUCTURE | daily_cash_position | required fields present | 6,101 | PASS |
| `S-ENUM-daily_cash_position` | STRUCTURE | daily_cash_position | values within allowed sets | 6,101 | PASS |
| `S-PAT-daily_cash_position` | STRUCTURE | daily_cash_position | IDs match their documented patterns | 6,101 | PASS |
| `S-MIN-daily_cash_position` | STRUCTURE | daily_cash_position | numeric minimums respected | 6,101 | PASS |
| `S-PK-entity_cash_position` | STRUCTURE | entity_cash_position | primary key unique and not null | 1,275 | PASS |
| `S-REQ-entity_cash_position` | STRUCTURE | entity_cash_position | required fields present | 1,275 | PASS |
| `S-ENUM-entity_cash_position` | STRUCTURE | entity_cash_position | values within allowed sets | 1,275 | PASS |
| `S-PAT-entity_cash_position` | STRUCTURE | entity_cash_position | IDs match their documented patterns | 1,275 | PASS |
| `S-MIN-entity_cash_position` | STRUCTURE | entity_cash_position | numeric minimums respected | 1,275 | PASS |
| `S-PK-exception` | STRUCTURE | exception | primary key unique and not null | 41 | PASS |
| `S-REQ-exception` | STRUCTURE | exception | required fields present | 41 | PASS |
| `S-ENUM-exception` | STRUCTURE | exception | values within allowed sets | 41 | PASS |
| `S-PAT-exception` | STRUCTURE | exception | IDs match their documented patterns | 41 | PASS |
| `S-MIN-exception` | STRUCTURE | exception | numeric minimums respected | 41 | PASS |
| `S-PK-exception_event` | STRUCTURE | exception_event | primary key unique and not null | 137 | PASS |
| `S-REQ-exception_event` | STRUCTURE | exception_event | required fields present | 137 | PASS |
| `S-ENUM-exception_event` | STRUCTURE | exception_event | values within allowed sets | 137 | PASS |
| `S-PAT-exception_event` | STRUCTURE | exception_event | IDs match their documented patterns | 137 | PASS |
| `S-MIN-exception_event` | STRUCTURE | exception_event | numeric minimums respected | 137 | PASS |
| `S-PK-audit_event` | STRUCTURE | audit_event | primary key unique and not null | 148 | PASS |
| `S-REQ-audit_event` | STRUCTURE | audit_event | required fields present | 148 | PASS |
| `S-ENUM-audit_event` | STRUCTURE | audit_event | values within allowed sets | 148 | PASS |
| `S-PAT-audit_event` | STRUCTURE | audit_event | IDs match their documented patterns | 148 | PASS |
| `S-MIN-audit_event` | STRUCTURE | audit_event | numeric minimums respected | 148 | PASS |
| `S-PK-forecast_vs_actual` | STRUCTURE | forecast_vs_actual | primary key unique and not null | 3,322 | PASS |
| `S-REQ-forecast_vs_actual` | STRUCTURE | forecast_vs_actual | required fields present | 3,322 | PASS |
| `S-ENUM-forecast_vs_actual` | STRUCTURE | forecast_vs_actual | values within allowed sets | 3,322 | PASS |
| `S-PAT-forecast_vs_actual` | STRUCTURE | forecast_vs_actual | IDs match their documented patterns | 3,322 | PASS |
| `S-MIN-forecast_vs_actual` | STRUCTURE | forecast_vs_actual | numeric minimums respected | 3,322 | PASS |
| `S-PK-variance_attribution` | STRUCTURE | variance_attribution | primary key unique and not null | 15,973 | PASS |
| `S-REQ-variance_attribution` | STRUCTURE | variance_attribution | required fields present | 15,973 | PASS |
| `S-ENUM-variance_attribution` | STRUCTURE | variance_attribution | values within allowed sets | 15,973 | PASS |
| `S-PAT-variance_attribution` | STRUCTURE | variance_attribution | IDs match their documented patterns | 15,973 | PASS |
| `S-MIN-variance_attribution` | STRUCTURE | variance_attribution | numeric minimums respected | 15,973 | PASS |
| `I-FK-currency` | INTEGRITY | currency | every foreign key resolves | 5 | PASS |
| `I-UNQ-currency` | INTEGRITY | currency | unique columns and natural keys | 5 | PASS |
| `I-FK-app_user` | INTEGRITY | app_user | every foreign key resolves | 11 | PASS |
| `I-UNQ-app_user` | INTEGRITY | app_user | unique columns and natural keys | 11 | PASS |
| `I-FK-counterparty` | INTEGRITY | counterparty | every foreign key resolves | 130 | PASS |
| `I-UNQ-counterparty` | INTEGRITY | counterparty | unique columns and natural keys | 130 | PASS |
| `I-FK-currency_rate` | INTEGRITY | currency_rate | every foreign key resolves | 972 | PASS |
| `I-UNQ-currency_rate` | INTEGRITY | currency_rate | unique columns and natural keys | 972 | PASS |
| `I-FK-liquidity_scenario` | INTEGRITY | liquidity_scenario | every foreign key resolves | 4 | PASS |
| `I-UNQ-liquidity_scenario` | INTEGRITY | liquidity_scenario | unique columns and natural keys | 4 | PASS |
| `I-FK-scenario_assumption` | INTEGRITY | scenario_assumption | every foreign key resolves | 10 | PASS |
| `I-UNQ-scenario_assumption` | INTEGRITY | scenario_assumption | unique columns and natural keys | 10 | PASS |
| `I-FK-scenario_assumption_link` | INTEGRITY | scenario_assumption_link | every foreign key resolves | 22 | PASS |
| `I-UNQ-scenario_assumption_link` | INTEGRITY | scenario_assumption_link | unique columns and natural keys | 22 | PASS |
| `I-FK-legal_entity` | INTEGRITY | legal_entity | every foreign key resolves | 5 | PASS |
| `I-UNQ-legal_entity` | INTEGRITY | legal_entity | unique columns and natural keys | 5 | PASS |
| `I-FK-bank_account` | INTEGRITY | bank_account | every foreign key resolves | 25 | PASS |
| `I-UNQ-bank_account` | INTEGRITY | bank_account | unique columns and natural keys | 25 | PASS |
| `I-FK-receivable` | INTEGRITY | receivable | every foreign key resolves | 727 | PASS |
| `I-UNQ-receivable` | INTEGRITY | receivable | unique columns and natural keys | 727 | PASS |
| `I-FK-payable` | INTEGRITY | payable | every foreign key resolves | 594 | PASS |
| `I-UNQ-payable` | INTEGRITY | payable | unique columns and natural keys | 594 | PASS |
| `I-FK-cash_flow_forecast` | INTEGRITY | cash_flow_forecast | every foreign key resolves | 2,000 | PASS |
| `I-UNQ-cash_flow_forecast` | INTEGRITY | cash_flow_forecast | unique columns and natural keys | 2,000 | PASS |
| `I-FK-ledger_entry` | INTEGRITY | ledger_entry | every foreign key resolves | 10,000 | PASS |
| `I-UNQ-ledger_entry` | INTEGRITY | ledger_entry | unique columns and natural keys | 10,000 | PASS |
| `I-FK-settlement_allocation` | INTEGRITY | settlement_allocation | every foreign key resolves | 1,118 | PASS |
| `I-UNQ-settlement_allocation` | INTEGRITY | settlement_allocation | unique columns and natural keys | 1,118 | PASS |
| `I-FK-bank_statement` | INTEGRITY | bank_statement | every foreign key resolves | 4,367 | PASS |
| `I-UNQ-bank_statement` | INTEGRITY | bank_statement | unique columns and natural keys | 4,367 | PASS |
| `I-FK-bank_account_event` | INTEGRITY | bank_account_event | every foreign key resolves | 28 | PASS |
| `I-UNQ-bank_account_event` | INTEGRITY | bank_account_event | unique columns and natural keys | 28 | PASS |
| `I-FK-receivable_event` | INTEGRITY | receivable_event | every foreign key resolves | 1,393 | PASS |
| `I-UNQ-receivable_event` | INTEGRITY | receivable_event | unique columns and natural keys | 1,393 | PASS |
| `I-FK-payable_event` | INTEGRITY | payable_event | every foreign key resolves | 1,735 | PASS |
| `I-UNQ-payable_event` | INTEGRITY | payable_event | unique columns and natural keys | 1,735 | PASS |
| `I-FK-cf_revision` | INTEGRITY | cf_revision | every foreign key resolves | 2,398 | PASS |
| `I-UNQ-cf_revision` | INTEGRITY | cf_revision | unique columns and natural keys | 2,398 | PASS |
| `I-FK-forecast_run` | INTEGRITY | forecast_run | every foreign key resolves | 23 | PASS |
| `I-UNQ-forecast_run` | INTEGRITY | forecast_run | unique columns and natural keys | 23 | PASS |
| `I-FK-forecast_run_scenario` | INTEGRITY | forecast_run_scenario | every foreign key resolves | 68 | PASS |
| `I-UNQ-forecast_run_scenario` | INTEGRITY | forecast_run_scenario | unique columns and natural keys | 68 | PASS |
| `I-FK-forecast_run_item` | INTEGRITY | forecast_run_item | every foreign key resolves | 8,708 | PASS |
| `I-UNQ-forecast_run_item` | INTEGRITY | forecast_run_item | unique columns and natural keys | 8,708 | PASS |
| `I-FK-forecast_run_balance_input` | INTEGRITY | forecast_run_balance_input | every foreign key resolves | 518 | PASS |
| `I-UNQ-forecast_run_balance_input` | INTEGRITY | forecast_run_balance_input | unique columns and natural keys | 518 | PASS |
| `I-FK-forecast_run_fx_input` | INTEGRITY | forecast_run_fx_input | every foreign key resolves | 92 | PASS |
| `I-UNQ-forecast_run_fx_input` | INTEGRITY | forecast_run_fx_input | unique columns and natural keys | 92 | PASS |
| `I-FK-forecast_position` | INTEGRITY | forecast_position | every foreign key resolves | 29,029 | PASS |
| `I-UNQ-forecast_position` | INTEGRITY | forecast_position | unique columns and natural keys | 29,029 | PASS |
| `I-FK-scenario_assumption_effect` | INTEGRITY | scenario_assumption_effect | every foreign key resolves | 290 | PASS |
| `I-UNQ-scenario_assumption_effect` | INTEGRITY | scenario_assumption_effect | unique columns and natural keys | 290 | PASS |
| `I-FK-forecast_run_event` | INTEGRITY | forecast_run_event | every foreign key resolves | 93 | PASS |
| `I-UNQ-forecast_run_event` | INTEGRITY | forecast_run_event | unique columns and natural keys | 93 | PASS |
| `I-FK-daily_cash_position` | INTEGRITY | daily_cash_position | every foreign key resolves | 6,101 | PASS |
| `I-UNQ-daily_cash_position` | INTEGRITY | daily_cash_position | unique columns and natural keys | 6,101 | PASS |
| `I-FK-entity_cash_position` | INTEGRITY | entity_cash_position | every foreign key resolves | 1,275 | PASS |
| `I-UNQ-entity_cash_position` | INTEGRITY | entity_cash_position | unique columns and natural keys | 1,275 | PASS |
| `I-FK-exception` | INTEGRITY | exception | every foreign key resolves | 41 | PASS |
| `I-UNQ-exception` | INTEGRITY | exception | unique columns and natural keys | 41 | PASS |
| `I-FK-exception_event` | INTEGRITY | exception_event | every foreign key resolves | 137 | PASS |
| `I-UNQ-exception_event` | INTEGRITY | exception_event | unique columns and natural keys | 137 | PASS |
| `I-FK-audit_event` | INTEGRITY | audit_event | every foreign key resolves | 148 | PASS |
| `I-UNQ-audit_event` | INTEGRITY | audit_event | unique columns and natural keys | 148 | PASS |
| `I-FK-forecast_vs_actual` | INTEGRITY | forecast_vs_actual | every foreign key resolves | 3,322 | PASS |
| `I-UNQ-forecast_vs_actual` | INTEGRITY | forecast_vs_actual | unique columns and natural keys | 3,322 | PASS |
| `I-FK-variance_attribution` | INTEGRITY | variance_attribution | every foreign key resolves | 15,973 | PASS |
| `I-UNQ-variance_attribution` | INTEGRITY | variance_attribution | unique columns and natural keys | 15,973 | PASS |
| `I-JOIN-ledger-account` | INTEGRITY | ledger_entry | ledger entity and currency equal the account's | 10,000 | PASS |
| `I-EMBED-account` | INTEGRITY | bank_account | account ID embeds its entity ID | 25 | PASS |
| `I-JOIN-receivable-account` | INTEGRITY | receivable | document account belongs to the document entity | 727 | PASS |
| `I-JOIN-payable-account` | INTEGRITY | payable | document account belongs to the document entity | 594 | PASS |
| `I-JOIN-cash_flow_forecast-account` | INTEGRITY | cash_flow_forecast | document account belongs to the document entity | 2,000 | PASS |
| `I-EMBED-ledger-year` | INTEGRITY | ledger_entry | LED ID year equals the posting year | 10,000 | PASS |
| `I-EMBED-rate` | INTEGRITY | currency_rate | rate ID embeds date and currencies | 972 | PASS |
| `I-JOIN-user-entity` | INTEGRITY | app_user | only account holders carry an entity | 11 | PASS |
| `I-JOIN-statement-currency` | INTEGRITY | bank_statement | statement currency equals account currency | 4,367 | PASS |
| `I-JOIN-allocation` | INTEGRITY | settlement_allocation | one document per allocation, in its currency, on the posting date | 1,118 | PASS |
| `I-JOIN-revision-currency` | INTEGRITY | cf_revision | revision currency equals the item currency | 2,398 | PASS |
| `I-EMBED-run` | INTEGRITY | forecast_run | run ID embeds cutoff date and version | 23 | PASS |
| `D-AR-due` | DATES | receivable | invoice date on or before due date | 727 | PASS |
| `D-AP-due` | DATES | payable | bill date on or before due date | 594 | PASS |
| `D-LED-active` | DATES | ledger_entry | postings inside the account's active period | 10,000 | PASS |
| `D-LED-busday` | DATES | ledger_entry | postings on business days | 10,000 | PASS |
| `D-CFR-order` | DATES | cf_revision | revisions after the item, in order, numbered consecutively | 2,398 | PASS |
| `D-STM-recorded` | DATES | bank_statement | statements received after the day they cover | 4,367 | PASS |
| `D-receivable_event` | DATES | receivable_event | events not before the document was recorded | 1,393 | PASS |
| `D-payable_event` | DATES | payable_event | events not before the document was recorded | 1,735 | PASS |
| `D-RUN-horizon` | DATES | forecast_run | horizon starts at the cutoff, spans horizon_days, created on/after cutoff | 23 | PASS |
| `A-STM-rollforward` | ARITHMETIC | bank_statement | closing = opening + credits - debits | 4,367 | PASS |
| `A-STM-continuity` | ARITHMETIC | bank_statement | opening = previous closing; first opening = account opening balance | 4,367 | PASS |
| `A-ALLOC-ledger` | ARITHMETIC | settlement_allocation | allocations add up to their cash posting | 1,071 | PASS |
| `A-AR-settled` | ARITHMETIC | receivable | settled amount never exceeds the invoice; PAID means fully settled | 727 | PASS |
| `A-TRF-net` | ARITHMETIC | ledger_entry | transfers net to zero; FX legs agree at the recorded rate | 357 | PASS |
| `A-POS-rollforward` | ARITHMETIC | daily_cash_position | daily balances roll forward from the ledger | 6,101 | PASS |
| `A-POS-consolidation` | ARITHMETIC | entity_cash_position | entity totals equal the sum of their accounts in USD | 1,275 | PASS |
| `A-FCST-rollforward` | ARITHMETIC | forecast_position | projected balances roll forward | 29,029 | PASS |
| `A-SCN-attribution` | ARITHMETIC | scenario_assumption_effect | assumption effects add up to the scenario's difference from base | 45 | PASS |
| `A-VAR-explained` | ARITHMETIC | forecast_vs_actual | variance fully explained by drivers (residual 0) | 3,322 | PASS |
| `A-VAR-drilldown` | ARITHMETIC | variance_attribution | item-level attribution adds up to each driver | 1,129 | PASS |
| `L-bank_account` | LIFECYCLE | bank_account_event | bank_account events follow the state machine | 28 | PASS |
| `L-bank_account-status` | LIFECYCLE | bank_account | status_at_end equals the last event | 25 | PASS |
| `L-receivable` | LIFECYCLE | receivable_event | receivable events follow the state machine | 1,393 | PASS |
| `L-receivable-status` | LIFECYCLE | receivable | status_at_end equals the last event | 727 | PASS |
| `L-payable` | LIFECYCLE | payable_event | payable events follow the state machine | 1,735 | PASS |
| `L-payable-status` | LIFECYCLE | payable | status_at_end equals the last event | 594 | PASS |
| `L-cash_flow_forecast` | LIFECYCLE | cf_revision | cash_flow_forecast events follow the state machine | 2,398 | PASS |
| `L-forecast_run` | LIFECYCLE | forecast_run_event | forecast_run events follow the state machine | 93 | PASS |
| `L-forecast_run-status` | LIFECYCLE | forecast_run | status_at_end equals the last event | 23 | PASS |
| `L-exception` | LIFECYCLE | exception_event | exception events follow the state machine | 137 | PASS |
| `L-exception-status` | LIFECYCLE | exception | status_at_end equals the last event | 41 | PASS |
| `U-ROW-app_user` | DUPLICATES | app_user | no exact duplicate rows (ignoring the ID) | 11 | PASS |
| `U-ROW-counterparty` | DUPLICATES | counterparty | no exact duplicate rows (ignoring the ID) | 130 | PASS |
| `U-ROW-currency_rate` | DUPLICATES | currency_rate | no exact duplicate rows (ignoring the ID) | 972 | PASS |
| `U-ROW-liquidity_scenario` | DUPLICATES | liquidity_scenario | no exact duplicate rows (ignoring the ID) | 4 | PASS |
| `U-ROW-scenario_assumption` | DUPLICATES | scenario_assumption | no exact duplicate rows (ignoring the ID) | 10 | PASS |
| `U-ROW-legal_entity` | DUPLICATES | legal_entity | no exact duplicate rows (ignoring the ID) | 5 | PASS |
| `U-ROW-bank_account` | DUPLICATES | bank_account | no exact duplicate rows (ignoring the ID) | 25 | PASS |
| `U-ROW-receivable` | DUPLICATES | receivable | no exact duplicate rows (ignoring the ID) | 727 | PASS |
| `U-ROW-payable` | DUPLICATES | payable | no exact duplicate rows (ignoring the ID) | 594 | PASS |
| `U-ROW-cash_flow_forecast` | DUPLICATES | cash_flow_forecast | no exact duplicate rows (ignoring the ID) | 2,000 | PASS |
| `U-ROW-ledger_entry` | DUPLICATES | ledger_entry | no exact duplicate rows (ignoring the ID) | 10,000 | PASS |
| `U-ROW-settlement_allocation` | DUPLICATES | settlement_allocation | no exact duplicate rows (ignoring the ID) | 1,118 | PASS |
| `U-ROW-bank_statement` | DUPLICATES | bank_statement | no exact duplicate rows (ignoring the ID) | 4,367 | PASS |
| `U-ROW-bank_account_event` | DUPLICATES | bank_account_event | no exact duplicate rows (ignoring the ID) | 28 | PASS |
| `U-ROW-receivable_event` | DUPLICATES | receivable_event | no exact duplicate rows (ignoring the ID) | 1,393 | PASS |
| `U-ROW-payable_event` | DUPLICATES | payable_event | no exact duplicate rows (ignoring the ID) | 1,735 | PASS |
| `U-ROW-cf_revision` | DUPLICATES | cf_revision | no exact duplicate rows (ignoring the ID) | 2,398 | PASS |
| `U-ROW-forecast_run` | DUPLICATES | forecast_run | no exact duplicate rows (ignoring the ID) | 23 | PASS |
| `U-ROW-forecast_run_event` | DUPLICATES | forecast_run_event | no exact duplicate rows (ignoring the ID) | 93 | PASS |
| `U-ROW-exception` | DUPLICATES | exception | no exact duplicate rows (ignoring the ID) | 41 | PASS |
| `R-RECON-001` | ANOMALY | bank_statement | bank movement equals the booked ledger movement (opening + ledger = closing) | 4,367 | EXPECTED |
| `R-FX-001` | ANOMALY | currency_rate | a fixing exists for every business day | 972 | EXPECTED |
| `R-DUP` | ANOMALY | cash_flow_forecast | no cash flow forecast twice | 2,000 | EXPECTED |
| `R-CUR` | ANOMALY | cash_flow_forecast | no currency mixed without conversion | 2,000 | EXPECTED |
| `R-LEAK-001` | ANOMALY | forecast_run | runs only use records known before their cutoff | 23 | EXPECTED |
| `V-legal_entity` | VOLUME | legal_entity | exactly 5 rows | 5 | PASS |
| `V-bank_account` | VOLUME | bank_account | exactly 25 rows | 25 | PASS |
| `V-ledger_entry` | VOLUME | ledger_entry | exactly 10,000 rows | 10,000 | PASS |
| `V-cash_flow_forecast` | VOLUME | cash_flow_forecast | exactly 2,000 rows | 2,000 | PASS |
| `V-currencies` | VOLUME | bank_account | 5 currencies in use | 5 | PASS |
| `G-no-labels` | VOLUME | dataset | no ground-truth label columns inside the dataset | 34 | PASS |
