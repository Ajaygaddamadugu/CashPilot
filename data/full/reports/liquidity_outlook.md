# 13-week liquidity outlook — run `FCAST-2026-10-01-001` (cutoff 2026-10-01)

Available cash excludes restricted accounts. Entity figures are standalone (before cash pooling); the group pool covers entity shortfalls, which is the decision the alerts drive.

| Scenario | Opening available | Lowest available | Lowest on | Closing available | Entities below buffer | Funding gap |
|---|---|---|---|---|---|---|
| SCN-BASE-V01 | 693,919,697 | 688,946,890 | 2026-10-02 | 731,044,299 | 11 | 3,892,425 |
| SCN-DELAY-V01 | 690,625,589 | 668,022,019 | 2026-10-23 | 723,570,907 | 13 | 6,779,563 |
| SCN-STRESS-V02 | 646,750,440 | 620,815,731 | 2026-10-25 | 659,467,240 | 13 | 8,082,599 |

## What each documented assumption does to this forecast

Assumptions are applied in order to the same snapshot; their effects add up exactly to the difference from base.

| Scenario | # | Assumption | Parameter | Items changed | Δ net flow (USD) | Δ lowest group cash (USD) |
|---|---|---|---|---|---|---|
| SCN-DELAY-V01 | 1 | ASM-0001: Tier A customers pay on time even in a downturn | AR_DELAY_DAYS A = 0 | 0 | 0 | 0 |
| SCN-DELAY-V01 | 2 | ASM-0002: Tier B customers stretch payment by a week | AR_DELAY_DAYS B = 7 | 536 | 0 | -3,092,949 |
| SCN-DELAY-V01 | 3 | ASM-0003: Tier C customers stretch payment by three weeks | AR_DELAY_DAYS C = 21 | 286 | -860,131 | -12,870,702 |
| SCN-DELAY-V01 | 4 | ASM-0004: Tier D customers stretch payment by six weeks | AR_DELAY_DAYS D = 45 | 238 | -6,613,261 | -4,961,220 |
| SCN-STRESS-V02 | 1 | ASM-0001: Tier A customers pay on time even in a downturn | AR_DELAY_DAYS A = 0 | 0 | 0 | 0 |
| SCN-STRESS-V02 | 2 | ASM-0002: Tier B customers stretch payment by a week | AR_DELAY_DAYS B = 7 | 536 | 0 | -3,092,949 |
| SCN-STRESS-V02 | 3 | ASM-0003: Tier C customers stretch payment by three weeks | AR_DELAY_DAYS C = 21 | 286 | -860,131 | -12,870,702 |
| SCN-STRESS-V02 | 4 | ASM-0004: Tier D customers stretch payment by six weeks | AR_DELAY_DAYS D = 45 | 238 | -6,613,261 | -4,961,220 |
| SCN-STRESS-V02 | 5 | ASM-0005: 10% of tier C receipts are not collected in the horizon | AR_COLLECTION_RATE C = 0.90 | 286 | -3,678,776 | -67,818 |
| SCN-STRESS-V02 | 6 | ASM-0006: 40% of tier D receipts are not collected in the horizon | AR_COLLECTION_RATE D = 0.60 | 238 | -9,114,085 | 0 |
| SCN-STRESS-V02 | 7 | ASM-0007: Suppliers demand payment five days earlier | AP_TIMING_SHIFT_DAYS  = -5 | 805 | 0 | -12,181,578 |
| SCN-STRESS-V02 | 8 | ASM-0008: Small operating receipts fall 15% | RUN_RATE_INFLOW_FACTOR  = 0.85 | 390 | -18,192,822 | -4,108,418 |
| SCN-STRESS-V02 | 9 | ASM-0010: USD appreciates 10% against every other currency | FX_SHOCK_PCT USD = -10 | 2537 | 1,518,428 | -30,848,474 |

## Entities below their buffer

### SCN-BASE-V01

| Entity | Name | First breach | Days below | Largest shortfall (USD) |
|---|---|---|---|---|
| ENT-000019 | Northgate Engineering Ltd | 2026-10-02 | 87 | 1,499,421 |
| ENT-000011 | Mayfield Pharma K.K. | 2026-11-18 | 43 | 623,526 |
| ENT-000012 | Oakridge Energy Inc. | 2026-10-02 | 43 | 467,737 |
| ENT-000018 | Selwyn Analytics GmbH | 2026-10-15 | 43 | 410,289 |
| ENT-000025 | Marston Textiles Inc. | 2026-10-01 | 78 | 304,340 |
| ENT-000003 | Stonebridge Components GmbH | 2026-10-01 | 72 | 198,906 |
| ENT-000005 | Newbold Retail Pvt Ltd | 2026-11-25 | 14 | 182,614 |
| ENT-000021 | Linwood Retail Inc. | 2026-10-23 | 13 | 129,857 |
| ENT-000027 | Glenrock Energy Inc. | 2026-10-01 | 11 | 38,776 |
| ENT-000004 | Yarrow Components Ltd | 2026-10-15 | 4 | 26,278 |
| ENT-000008 | Dunmore Foods B.V. | 2026-10-02 | 3 | 10,681 |

### SCN-DELAY-V01

| Entity | Name | First breach | Days below | Largest shortfall (USD) |
|---|---|---|---|---|
| ENT-000019 | Northgate Engineering Ltd | 2026-10-02 | 90 | 1,680,243 |
| ENT-000005 | Newbold Retail Pvt Ltd | 2026-11-23 | 29 | 1,061,970 |
| ENT-000004 | Yarrow Components Ltd | 2026-10-15 | 44 | 970,972 |
| ENT-000012 | Oakridge Energy Inc. | 2026-10-02 | 55 | 652,708 |
| ENT-000011 | Mayfield Pharma K.K. | 2026-11-18 | 43 | 623,526 |
| ENT-000027 | Glenrock Energy Inc. | 2026-10-01 | 65 | 427,042 |
| ENT-000018 | Selwyn Analytics GmbH | 2026-10-15 | 64 | 415,308 |
| ENT-000025 | Marston Textiles Inc. | 2026-10-01 | 82 | 388,161 |
| ENT-000021 | Linwood Retail Inc. | 2026-10-23 | 13 | 246,381 |
| ENT-000003 | Stonebridge Components GmbH | 2026-10-01 | 79 | 224,145 |
| ENT-000017 | Bexley Logistics Inc. | 2026-10-23 | 5 | 45,796 |
| ENT-000008 | Dunmore Foods B.V. | 2026-10-02 | 9 | 39,972 |
| ENT-000015 | Redwater Analytics Pvt Ltd | 2026-12-01 | 1 | 3,341 |

### SCN-STRESS-V02

| Entity | Name | First breach | Days below | Largest shortfall (USD) |
|---|---|---|---|---|
| ENT-000019 | Northgate Engineering Ltd | 2026-10-01 | 91 | 1,761,724 |
| ENT-000005 | Newbold Retail Pvt Ltd | 2026-11-18 | 43 | 1,321,301 |
| ENT-000004 | Yarrow Components Ltd | 2026-10-15 | 76 | 1,042,884 |
| ENT-000012 | Oakridge Energy Inc. | 2026-10-01 | 64 | 790,979 |
| ENT-000011 | Mayfield Pharma K.K. | 2026-11-18 | 43 | 670,572 |
| ENT-000027 | Glenrock Energy Inc. | 2026-10-01 | 83 | 523,822 |
| ENT-000017 | Bexley Logistics Inc. | 2026-10-15 | 10 | 486,640 |
| ENT-000018 | Selwyn Analytics GmbH | 2026-10-04 | 81 | 417,201 |
| ENT-000025 | Marston Textiles Inc. | 2026-10-01 | 91 | 406,701 |
| ENT-000021 | Linwood Retail Inc. | 2026-10-18 | 19 | 279,456 |
| ENT-000003 | Stonebridge Components GmbH | 2026-10-01 | 84 | 254,665 |
| ENT-000015 | Redwater Analytics Pvt Ltd | 2026-11-08 | 19 | 71,180 |
| ENT-000008 | Dunmore Foods B.V. | 2026-10-01 | 32 | 55,473 |

## Alerts raised on this run

37 liquidity alerts (rule R-LIQ-001), all worked through the playbook: RESOLVED: 37.
