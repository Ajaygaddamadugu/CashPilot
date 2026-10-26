# 13-week liquidity outlook — run `FCAST-2026-10-01-001` (cutoff 2026-10-01)

Available cash excludes restricted accounts. Entity figures are standalone (before cash pooling); the group pool covers entity shortfalls, which is the decision the alerts drive.

| Scenario | Opening available | Lowest available | Lowest on | Closing available | Entities below buffer | Funding gap |
|---|---|---|---|---|---|---|
| SCN-BASE-V01 | 35,434,119 | 33,311,365 | 2026-10-04 | 39,416,691 | 2 | 2,989,653 |
| SCN-DELAY-V01 | 35,104,271 | 29,627,016 | 2026-10-23 | 37,691,248 | 2 | 3,875,946 |
| SCN-STRESS-V02 | 32,101,686 | 25,722,165 | 2026-10-25 | 31,750,961 | 2 | 4,660,943 |

## What each documented assumption does to this forecast

Assumptions are applied in order to the same snapshot; their effects add up exactly to the difference from base.

| Scenario | # | Assumption | Parameter | Items changed | Δ net flow (USD) | Δ lowest group cash (USD) |
|---|---|---|---|---|---|---|
| SCN-DELAY-V01 | 1 | ASM-0001: Tier A customers pay on time even in a downturn | AR_DELAY_DAYS A = 0 | 0 | 0 | 0 |
| SCN-DELAY-V01 | 2 | ASM-0002: Tier B customers stretch payment by a week | AR_DELAY_DAYS B = 7 | 76 | 0 | -341,452 |
| SCN-DELAY-V01 | 3 | ASM-0003: Tier C customers stretch payment by three weeks | AR_DELAY_DAYS C = 21 | 37 | -505,813 | -2,675,821 |
| SCN-DELAY-V01 | 4 | ASM-0004: Tier D customers stretch payment by six weeks | AR_DELAY_DAYS D = 45 | 27 | -1,219,631 | -667,076 |
| SCN-STRESS-V02 | 1 | ASM-0001: Tier A customers pay on time even in a downturn | AR_DELAY_DAYS A = 0 | 0 | 0 | 0 |
| SCN-STRESS-V02 | 2 | ASM-0002: Tier B customers stretch payment by a week | AR_DELAY_DAYS B = 7 | 76 | 0 | -341,452 |
| SCN-STRESS-V02 | 3 | ASM-0003: Tier C customers stretch payment by three weeks | AR_DELAY_DAYS C = 21 | 37 | -505,813 | -2,675,821 |
| SCN-STRESS-V02 | 4 | ASM-0004: Tier D customers stretch payment by six weeks | AR_DELAY_DAYS D = 45 | 27 | -1,219,631 | -667,076 |
| SCN-STRESS-V02 | 5 | ASM-0005: 10% of tier C receipts are not collected in the horizon | AR_COLLECTION_RATE C = 0.90 | 37 | -548,858 | -30,000 |
| SCN-STRESS-V02 | 6 | ASM-0006: 40% of tier D receipts are not collected in the horizon | AR_COLLECTION_RATE D = 0.60 | 27 | -1,376,583 | 0 |
| SCN-STRESS-V02 | 7 | ASM-0007: Suppliers demand payment five days earlier | AP_TIMING_SHIFT_DAYS  = -5 | 65 | 0 | -1,414,566 |
| SCN-STRESS-V02 | 8 | ASM-0008: Small operating receipts fall 15% | RUN_RATE_INFLOW_FACTOR  = 0.85 | 65 | -1,856,866 | -426,225 |
| SCN-STRESS-V02 | 9 | ASM-0010: USD appreciates 10% against every other currency | FX_SHOCK_PCT USD = -10 | 300 | 375,682 | -2,034,060 |

## Entities below their buffer

### SCN-BASE-V01

| Entity | Name | First breach | Days below | Largest shortfall (USD) |
|---|---|---|---|---|
| ENT-000001 | Ravensworth Group Holdings Inc. | 2026-10-02 | 50 | 2,207,722 |
| ENT-000004 | Yarrow Components Pvt Ltd | 2026-12-14 | 17 | 781,931 |

### SCN-DELAY-V01

| Entity | Name | First breach | Days below | Largest shortfall (USD) |
|---|---|---|---|---|
| ENT-000001 | Ravensworth Group Holdings Inc. | 2026-10-02 | 68 | 2,237,566 |
| ENT-000004 | Yarrow Components Pvt Ltd | 2026-11-02 | 51 | 1,638,379 |

### SCN-STRESS-V02

| Entity | Name | First breach | Days below | Largest shortfall (USD) |
|---|---|---|---|---|
| ENT-000001 | Ravensworth Group Holdings Inc. | 2026-10-01 | 75 | 3,023,932 |
| ENT-000004 | Yarrow Components Pvt Ltd | 2026-10-28 | 64 | 1,637,011 |

## Alerts raised on this run

6 liquidity alerts (rule R-LIQ-001), all worked through the playbook: RESOLVED: 6.
