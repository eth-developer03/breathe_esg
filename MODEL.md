# Data Model

## Overview

The model has four layers, each with a distinct purpose:

```
FILE UPLOAD
    ↓
ImportBatch     — one upload event, parse statistics
    ↓
RawRecord       — immutable snapshot of one source row (NEVER updated)
    ↓
NormalizedRecord — analyst-facing, reviewable, editable record
    + AuditEvent — append-only log of every state change
```

This layering is deliberate. The split between RawRecord and NormalizedRecord means auditors can always trace any approved figure back to the exact bytes that arrived in the file. NormalizedRecord can be edited by analysts; RawRecord cannot.

---

## Models

### Organization
Multi-tenancy root. Every other model carries an `org` foreign key. Application-level scoping (not database row-level security) because it's simpler to implement and audit, and the expected scale (dozens of orgs, not millions) doesn't require pg_rls.

**Why `plant_lookup` and `cost_center_lookup` here:** SAP plant codes (`1000`, `PLNT_MAN`) are meaningless without a translation table, and this table varies per client. Storing it on the org lets analysts see `Manchester Plant (UK)` instead of `1000` without modifying the source data.

### DataSource
One configured source per integration type. Stores source-specific config: which SAP plants to include, which utility account numbers, which Concur cost centers. This lets us distinguish "plant 1000 SAP export" from "plant 2000 SAP export" even though both use the same parser.

### ImportBatch
One file upload → one batch. Tracks `file_hash` (SHA-256) to detect re-uploads of the same file and warn the user. Stores parse statistics (`total_rows`, `success_rows`, `error_rows`, `warning_rows`) and structured error details with row numbers, so an analyst can go back to the source file and fix the bad rows.

### RawRecord (IMMUTABLE)
**Never modified after creation.** Stores:
- `source_row_number`: which line in the original file
- `raw_data`: the original field names and values, exactly as ingested (JSON)
- `parse_status`: OK / ERROR / SKIPPED
- `parse_error`: human-readable description if parsing failed

No `updated_at` field — intentional. Removing it makes immutability visible at the schema level. If an auditor asks "what did row 47 of this file actually say?", this is the answer.

### NormalizedRecord
The primary entity analysts interact with. Derived from RawRecord but can be edited. Key design decisions:

**Scope classification** is stored as an integer (1, 2, or 3), not derived at read time. Classification is deterministic at ingest:
- SAP fuel movements → Scope 1 (direct combustion)
- Utility electricity → Scope 2 (purchased electricity)
- Corporate travel → Scope 3 Category 6 (business travel)
- SAP procurement of goods → Scope 3 Category 1 (purchased goods)

**Separate `raw_quantity`/`raw_unit` and `normalized_quantity`/`normalized_unit`:** The raw pair preserves what came in (e.g., `5000, L` or `5,000.000, KG`). The normalized pair is always in the canonical unit for that category:
- Fuel → litres (L)
- Electricity → kilowatt-hours (kWh)
- Flights → passenger-km (pkm) estimated from airport codes
- Hotels → room-nights
- Ground transport → km

**`period_start` / `period_end` alongside `activity_date`:** Utility billing periods don't align to calendar months. A December bill might cover Nov 18 – Dec 19. Storing both the period window and a canonical `activity_date` (= period end) lets us: (a) report on calendar months without losing billing period accuracy, and (b) detect period gaps between consecutive meter records.

**`flags` as a JSON list of string codes:** Codes are computed at normalization time. Possible flags:
- `ZERO_QUANTITY` — quantity is zero
- `NEGATIVE_QUANTITY` — negative (likely a reversal, not a normal movement)
- `FUTURE_DATE` — activity date is in the future
- `STALE_DATE` — date is > 2 years old
- `UNKNOWN_FACILITY` — plant code not in org's lookup table
- `STATISTICAL_OUTLIER` — quantity > 3× the rolling 6-month average for this facility/category
- `MISSING_EMISSION_FACTOR` — no emission factor found for this category/year
- `DUPLICATE_CANDIDATE` — another record with same date, facility, and quantity already exists
- `PERIOD_GAP` — no prior billing period record found for this meter (utility only)

**`original_values` + `was_edited`:** On first analyst edit, we snapshot all editable fields into `original_values` (JSON). Combined with AuditEvent, this gives a full before/after trail. We don't copy the entire record on every edit — just the fields that changed and the pre-edit snapshot taken on first edit.

**`status` workflow:**
```
PENDING → FLAGGED (if flags detected at ingest)
PENDING → APPROVED (analyst approves)
FLAGGED → APPROVED (analyst reviews flags and approves)
PENDING/FLAGGED → REJECTED (analyst rejects, reason required)
APPROVED/REJECTED → PENDING (analyst re-opens, logged in audit trail)
```
Approved records are the only ones that flow to audit-ready reporting.

### EmissionFactor
Conversion factors from authoritative sources. Key design choices:
- `category` is a slug string (`diesel`, `flight_economy_long`, `hotel_uk`) rather than an enum — this allows adding new categories without a migration.
- `year` field allows versioning. When calculating historical emissions (e.g., 2022 fuel data), we use the 2022 factor, not the current one. This is a GHG Protocol requirement.
- `scope` is stored here to avoid re-deriving it — the factor's scope is an inherent property (electricity is always Scope 2).

Sources used:
- DEFRA 2023 GHG Conversion Factors (UK government, freely available, widely accepted by UK and international auditors)
- EPA eGRID 2022 (US electricity grid sub-regional factors)
- Cornell Hotel Sustainability Benchmarking Index (hotel factors)

### AuditEvent (APPEND-ONLY)
No admin `has_change_permission`. No `updated_at`. Every significant state change creates a new row:
- `BATCH_UPLOADED` — file ingested
- `RECORD_APPROVED` / `RECORD_REJECTED` — analyst decision
- `RECORD_EDITED` — field changed (reason required)
- `RECORD_FLAGGED` — manual flag added
- `RECORD_REOPENED` — status reset to PENDING

`before_state` and `after_state` are JSON snapshots of the relevant fields. We don't snapshot the entire record — just what changed — to keep the audit log readable.

`ip_address` is stored for forensic completeness.

---

## Multi-Tenancy

Every model that holds data carries an `org` FK. All querysets are filtered by the request user's org via `get_user_org(request)`. There is no cross-org data leakage possible at the application layer.

We do not use database row-level security (pg_rls) because:
1. The expected scale doesn't require it
2. pg_rls adds complexity to migrations and debugging
3. Application-level filtering is easier to audit and test

---

## What This Model Does Not Handle

- **Market-based Scope 2 accounting** (REGOs, PPAs): The model stores location-based factors only. A column `emission_factor_market_based` could be added when the client provides renewable energy certificates.
- **Sub-location granularity within a plant**: All fuel movements from plant `1000` roll up together. If a plant has multiple sub-processes that need separate Scope 1 reporting, the `facility_code` would need a hierarchical model.
- **Multi-year reporting period**: Records are date-stamped but there's no formal `reporting_year` field. The frontend filters by date range. This is fine for a prototype but a production system would want an explicit `reporting_period` entity.
