# ID conventions

The five formats required by the brief are used exactly as given. Every other table follows
the same pattern: a type prefix, the cycle year and a zero-padded counter. IDs are assigned
**once**, in a documented sort order, and never re-assigned; every reference to an ID uses
exactly the same string in every file (checked by the validator: `I-FK-*`, `I-EMBED-*`).

| Table | Format | Example | Assigned in order of |
|---|---|---|---|
| legal_entity | `ENT-` + 6 digits | `ENT-000001` (the holding) | generation order |
| bank_account | `BANKACC-<entity-id>-` + 3 digits | `BANKACC-ENT-000001-001` | account sequence within the entity |
| ledger_entry | `LED-<posting year>-` + 8 digits | `LED-2026-00000001` | posting date, recorded time, account |
| cash_flow_forecast | `CF-<cycle year>-` + 6 digits | `CF-2026-000001` | recorded time, entity, category, reference |
| forecast_run | `FCAST-<cutoff date>-` + 3-digit version | `FCAST-2026-01-01-001` | version within the cutoff date |
| receivable / payable | `AR-` / `AP-<cycle year>-` + 6 digits | `AR-2026-000001` | recorded time, entity, document date |
| invoice / bill number | `INV-` / `BILL-<entity no>-` + 6 digits | `INV-000003-000042` | recorded order within the entity |
| currency_rate | `FXR-<rate date>-<base>-USD` | `FXR-2026-03-05-EUR-USD` | natural key (date, currency) |
| liquidity_scenario | `SCN-<family>-V` + 2 digits | `SCN-STRESS-V02` | version within the family |
| scenario_assumption | `ASM-` + 4 digits | `ASM-0007` | definition order |
| counterparty / app_user | `CPTY-` + 6 / `USR-` + 4 digits | `CPTY-000123`, `USR-0003` | generation order |
| cf_revision | `CFR-<cycle year>-` + 7 digits | `CFR-2026-0000001` | recorded time, item, revision number |
| settlement_allocation | `SETL-<cycle year>-` + 7 digits | `SETL-2026-0000001` | allocation date, ledger entry, document |
| bank_statement | `STM-<cycle year>-` + 7 digits | `STM-2026-0000001` | statement date, account |
| event tables | `BAE-`, `ARE-`, `APE-`, `FRE-`, `EXE-`, `AUD-` + year + counter | `FRE-2026-000001` | event time (new events continue the sequence) |
| exception | `EXC-<cycle year>-` + 6 digits | `EXC-2026-000001` | detection time, rule, record |
| internal transfer group | `TRF-<cycle year>-` + 6 digits | `TRF-2026-000001` | first leg in ledger order |
| variance_attribution | `VA-` + 9 digits | `VA-000000001` | run, entity, week, driver, record |
| ground truth | `GT-` + 6 digits | `GT-000001` | label, issue type, record |

Notes

* The **cycle year** (2026) is used for all sequence counters, including invoices carried in
  from late 2025, so that one year's sequence is contiguous. Ledger IDs use the posting year
  (all postings fall in 2026) and rate IDs use the fixing date.
* IDs that embed other IDs are validated: the `BANKACC-` prefix must equal the account's
  `entity_id`; the `FCAST-` date and version must equal `cutoff_date` and `version`; the rate ID
  must equal its date and currency pair; the `LED-` year must equal the posting year.
* Injected duplicate forecast items take the next free `CF-` numbers at the end of the
  sequence (IDs are immutable, so nothing is renumbered). Detectors never use ID order.
* New events appended by the workflow continue the existing sequence of their table.
