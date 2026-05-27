# Decisions

Every ambiguity I resolved, what I chose, why, and what I'd ask the PM.

---

## SAP: Which export format?

**The options:** IDoc (SAP's native EDI format), OData service (REST-ish), BAPI (function call), flat file from ALV list viewer.

**What I chose:** Tab-delimited flat file from transaction MB51 (Material Document List).

**Why:**
- IDoc requires SAP middleware (SAP PI/PO or Integration Suite) that not every customer has configured for outbound to a third party. Even when it exists, the setup requires Basis involvement and weeks of lead time.
- OData requires SAP Gateway to be configured and exposed. Gateway setup is an IT project, not something a sustainability coordinator can trigger. Many older SAP versions (ECC 6.0, still widespread) have limited OData support.
- BAPI requires RFC connectivity — direct network access to SAP, credentials, and SAP-specific client libraries. This is a security discussion that drags in the client's CISO.
- Flat file from MB51 is what a facilities manager or sustainability lead can actually do without IT: open SAP, run the transaction, press "Export to spreadsheet," email the file. It works on every SAP system ever shipped.

**The German column headers:** On German-language SAP systems (common in European enterprises — especially German, Austrian, Swiss clients), MB51 exports use German field labels: `Buchungsdatum` (posting date), `Werk` (plant), `Menge` (quantity), `ME` (unit of measure). Our parser maps both German and English variants.

**Scope of SAP data handled:**
- Fuel goods issues (movement types 201, 261, 291) — these represent direct fuel consumption = Scope 1
- Material categories: diesel, petrol, natural gas (M3), LPG, heating oil
- One fiscal year per export. Multi-year is out of scope for this prototype.
- Not handled: SAP procurement (EKKO/EKPO) — I'd need to understand which procurement categories the client wants in Scope 3

**What I'd ask the PM:**
1. Does this client have SAP in German or English? (Affects column header mapping)
2. Which plant codes are in scope? (Need the lookup table; currently hardcoded in demo seed)
3. Do they want procurement data from SAP for Scope 3 Category 1, or just fuel?
4. Are reversals (movement type 102) expected? Currently excluded.

---

## Utility: Which ingestion mode?

**The options:** PDF bill parsing, portal CSV export, Green Button API (ESPI protocol), EDI 867 (for large commercial accounts), manual entry.

**What I chose:** Portal CSV export, modelled on the Green Button format.

**Why:**
- PDF parsing is brittle. Every utility has a different bill layout, and layouts change silently when the utility updates their billing system. We'd need OCR + template matching per utility, which is a maintenance burden.
- Green Button Connect (ESPI/OAuth API) is the cleanest option but requires per-utility OAuth setup. Even among the ~60% of US utilities that implement Green Button, the customer portal must have the Connect feature enabled (not all do), and the client needs to authorize our app. This is a 2-4 week onboarding overhead per utility.
- EDI 867 (Usage Data) is real but only available for large C&I (commercial & industrial) accounts with dedicated account managers. Not available for most multi-site enterprise clients.
- Portal CSV is what the facilities team actually does every month: log in, click "Download usage data", pick the date range, save the CSV. It's the path of least resistance and works for 95% of utility accounts.

**Billing period misalignment:** Utility billing periods don't align to calendar months. National Grid in the UK typically bills on a ~30-day cycle that started when the meter was installed, not on the 1st of the month. A "December" bill might cover Nov 18 – Dec 19. We handle this by:
1. Storing `period_start` and `period_end` separately from `activity_date`
2. Setting `activity_date` = `period_end` (the conventional attribution point for the period)
3. Detecting `PERIOD_GAP` when a meter's consecutive billing periods have a gap > 45 days

**kW vs kWh:** Peak demand (kW) is an instantaneous measurement used for demand charges on industrial tariffs. Consumption (kWh) is what we need for Scope 2 emissions. The parser extracts both but only uses kWh for emission calculations.

**What I'd ask the PM:**
1. Is this a UK client (National Grid / WPD) or US (PG&E, ConEd, Duke)? The emission factors differ significantly.
2. Do they have REGOs (Renewable Energy Guarantees of Origin) for any meters? If so, Scope 2 market-based factor changes.
3. How many meters? If > 50, the manual CSV download process becomes painful — worth discussing Green Button Connect.
4. Is there sub-metering? (e.g., one meter per floor) — affects how we roll up to facility level.

---

## Travel: Which platform and format?

**The options:** Concur API, Concur CSV export, Navan CSV export, AmexGBT report, manual entry from receipts.

**What I chose:** Concur expense report CSV export ("Analyze" report).

**Why:**
- SAP Concur is used by ~70% of Fortune 500 companies for T&E. Navan is growing (especially tech sector) but Concur remains dominant in enterprise.
- The Concur API exists (REST + OData) but accessing it requires OAuth app registration, which is an IT/procurement process. The client's travel admin or sustainability lead cannot do this unilaterally.
- The "Analyze" report builder in Concur produces a CSV with every field we need. It's a self-service capability available to any report admin. No API credentials, no IT involvement.
- Navan and AmexGBT can export similar CSVs. Our column mapping handles variant field names.

**Airport codes instead of distances:** Concur records flights as airport codes (LHR, JFK) without distances. We use great-circle calculations from a pre-computed coordinate table (~50 major airports). For routes not in the table, we have no fallback distance and flag the record as `MISSING_EMISSION_FACTOR` rather than silently using a wrong estimate.

**Emission factor selection by haul and cabin:**
- Short-haul: < 3,700 km (roughly London to Istanbul, or NYC to Miami)
- Long-haul: ≥ 3,700 km
- Cabin class: economy < business (~2.9×) < first (~4×) — the multiplier reflects seat size allocation per DEFRA methodology
- Radiative forcing factor of 1.891× is baked into the DEFRA factors (it's included in their figures, not a separate multiplier)

**What I'd ask the PM:**
1. Is the client on Concur or another platform (Navan, Egencia, AmexGBT)?
2. Do they want to include mileage reimbursement (personal vehicle) in Scope 3? Currently we handle it as ground_transport but the emission factor (per km, personal car) differs from rental cars.
3. Should hotel emissions use a country-specific factor rather than UK/global average? The Cornell index has country-level data.
4. Do they want employee-level granularity or just department/cost center rollup?

---

## Emission factors: Which source?

**Chose DEFRA 2023 GHG Conversion Factors** for UK-based operations (fuel, electricity, travel). Reasons:
- Freely available, published annually, used by UK government and widely accepted by auditors
- Covers all relevant categories: fuel combustion, UK grid electricity, flights (by haul and class), hotel, ground transport
- Includes upstream (well-to-wheel) emissions, not just combustion

**Chose EPA eGRID 2022** for US electricity. DEFRA doesn't cover non-UK grids. The US has significant sub-regional variation (WECC vs SERC) — for the prototype we use the national average but the data model is designed to support sub-regional factors.

**Year versioning:** Emission factors change each year. A record from 2022 should use 2022 factors. We query `year__lte=activity_year ORDER BY year DESC` to get the most recent applicable factor.

---

## Scope classification logic

| Source | Material/Type | Scope | GHG Protocol Category |
|--------|--------------|-------|----------------------|
| SAP MB51 | Diesel, petrol, LPG, natural gas | 1 | Stationary/mobile combustion |
| SAP MB51 | Heating oil | 1 | Stationary combustion |
| Utility | Electricity | 2 | Purchased electricity |
| Travel | Flights | 3 | Category 6: Business Travel |
| Travel | Hotels | 3 | Category 6: Business Travel |
| Travel | Ground transport | 3 | Category 6: Business Travel |

SAP procurement of goods (purchase orders) would be Scope 3 Category 1 (Purchased Goods & Services), but I've excluded it from the prototype — see TRADEOFFS.md.

---

## Review workflow: require reason for rejection, not for approval

**Decision:** Rejection requires a text reason. Approval does not (but supports optional notes).

**Why:** An approved record says "I've reviewed this, it's correct." That's the expected outcome. A rejected record says "this data is wrong" — auditors need to know *why*. The reason also creates a paper trail for the data provider (e.g., "Q: why was row 45 rejected? A: the quantity was 10× higher than all surrounding months, vendor confirmed it was a typo").

---

## Bulk approve: available, no reason required

**Decision:** Analysts can select multiple PENDING/FLAGGED records and approve them in batch. No per-record reason required.

**Why:** In a real deployment, an analyst might receive 500 SAP rows at once. Requiring them to write a note for every routine approval would make the UX unusable. Bulk approve is intended for records that look obviously correct (no flags, consistent with history). Flagged records can be bulk-approved too — the analyst is making an informed decision that the flags are acceptable (e.g., they've verified with the plant manager that a high-consumption month was due to a one-off operation).

The audit log records that bulk approval happened and who performed it.
