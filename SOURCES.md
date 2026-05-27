# Sources

For each data source: what I researched, what I learned, what the sample data looks like and why, and what would break in a real deployment.

---

## 1. SAP Fuel & Procurement Data

### What I researched

SAP's material document architecture. The relevant tables are:
- **MKPF** (Material Document Header): document number, company code, posting date, document date
- **MSEG** (Material Document Segment): one row per material per movement. Contains plant (WERKS), storage location (LGORT), material number (MATNR), movement type (BWART), quantity (MENGE), unit (MEINS), vendor (LIFNR)

Transaction **MB51** (Material Document List) joins these tables and allows export via the ALV List Viewer (System → List → Export → Spreadsheet). The output is tab-delimited with one header row.

Movement types that represent fuel consumption:
- **201**: Goods issue to cost center — the most common for fuel drawn from a central tank
- **261**: Goods issue for production order — fuel used in manufacturing
- **291**: Goods issue for project (WBS element)
- **501**: Receipt without purchase order (not relevant for emissions)

SAP unit codes for liquid/gas fuels:
- **L** or **LT** → litres
- **M3** → cubic metres (natural gas)
- **KG** → kilograms (LPG sometimes stored by weight)
- **GJ** → gigajoules (rarely)

On German-language SAP systems, column headers appear in German. The most common German labels I found in documentation and community forums:
- `Buchungsdatum` = posting date
- `Belegjahr` = document year
- `Werk` = plant
- `Material` = material number
- `Materialkurztext` = material description (short text)
- `Menge` = quantity
- `ME` = unit of measure (Maßeinheit)
- `Bewegungsart` = movement type
- `Lieferant` = vendor

German number format: `5.000,000` means 5,000.000 (dot = thousands separator, comma = decimal).

### What the sample data looks like and why

`sap_mb51_fuel_q1_2024.txt` contains 20 rows covering Q1 2024 for plants 1000, 2000, and 3000 (the three sites in the demo org).

Materials included:
- `DIESEL001` (Dieselkraftstoff EN590) — standard European diesel specification, `L` unit
- `BENZIN001` (Motorenbenzin Super 95) — unleaded petrol, `L` unit
- `ERDGAS01` (Erdgas H) — high-calorific natural gas, `M3` unit
- `LPG00001` (Fluessiggas Propan) — LPG for heating/forklifts, `L` unit
- `HEIZOEL1` (Heizöl EL) — heating oil, `L` unit

EN590 is the EU standard for road diesel — I used this descriptor because it's what actually appears in SAP material masters at European industrial sites. `Motorenbenzin Super 95` is the German name for 95-octane unleaded petrol.

Vendors are coded (`SHELL_UK_001`, `BP_UK_002`) as they appear in SAP — the vendor name is stored in LFM1/LFA1 tables and not typically in the MB51 export. The parser preserves the code; an analyst lookup table would be needed to resolve names.

Quantities are in German decimal format (`5.000,000`) to test the `_parse_sap_quantity` function.

### What would break in a real deployment

1. **Character encoding**: SAP exports in SAP code page 1100 (a Windows-1252 variant) on some systems. Our parser tries UTF-8 then falls back to latin-1. A system with umlauts in vendor names (Würth GmbH) using a non-standard encoding would produce garbled text.

2. **Column order is not guaranteed**: MB51's column order depends on which columns the user has in their layout. If a user has rearranged or hidden columns, the header map breaks. A robust solution would require the client to save and always use a specific ALV layout.

3. **Material descriptions aren't fuel keywords on all systems**: Our fuel detection uses keyword matching (`diesel`, `benzin`, etc.). A client using English SAP with custom material descriptions (`FUEL-DIRECT-CHARGEABLE` or `OIL-LUBRICANT`) would need their material master checked manually to distinguish fuel from other goods.

4. **Movement type reversals**: Movement type 102 (reversal of 101 goods receipt) or 202 (reversal of 201 goods issue) appear in MB51 as negative quantities. Our parser flags `NEGATIVE_QUANTITY`. In reality, reversals need to be matched to their originals and netted — we currently don't do this.

5. **Multiple company codes**: Large enterprises have multiple company codes. MB51 filters by plant, which crosses company codes. The `org` field handles this at the tenant level, but inter-company netting (plant 1000 in company code 100 transferring fuel to plant 2000 in company code 200) would double-count.

---

## 2. Utility Electricity Data

### What I researched

Green Button is the ANSI/NAESB standard (REQ.21) for utility data exchange, adopted by ~60% of US electric utilities. The standard defines two modes:
- **Green Button Download My Data**: CSV or XML download from the utility portal
- **Green Button Connect My Data**: OAuth-based API (ESPI protocol) where a third party can request data directly

The CSV format produced by Green Button Download typically contains either:
- **Interval data** (15-minute or hourly readings): timestamp, kWh per interval
- **Summary/billing data**: account, meter, billing period, total kWh, peak demand, bill amount

We handle the billing summary format because it's what a facilities team actually downloads for ESG reporting — interval data (96 readings per day per meter) is too granular for carbon accounting.

UK utilities (National Grid, WPD, ScottishPower) don't formally implement Green Button but produce structurally similar portal CSV exports.

### What the sample data looks like and why

`utility_electricity_q1_2024.csv` covers three meters across two sites (Manchester plant, Birmingham DC) for billing cycles spanning Nov 2023 – Mar 2024.

Key design choices in the sample data:
- **Billing periods don't start on the 1st**: MTR-A102 bills on the 18th, MTR-B205 on the 15th, MTR-C301 on the 20th. This reflects real-world meter installation dates.
- **Different meters have different billing cycles**: A common source of confusion when aggregating multiple sites.
- **Peak demand (kW)**: Included because it appears in real exports and is relevant for industrial tariff analysis, even though we don't use it for emission calculations.
- **Rate schedule codes**: `I-6 Industrial TOU` (Time-of-Use, industrial) and `I-4 Commercial` are realistic National Grid tariff codes. These are noted in the record description.
- **Amounts in GBP**: Real UK utility bills are in GBP. The parser strips currency symbols.

### What would break in a real deployment

1. **Multi-row preamble**: Some utility portals add account summary information above the data table. Our parser scans for the header row by looking for `kWh`, `Consumption`, or `Usage` keywords. A portal with neither keyword in the header would fail.

2. **Estimated vs actual reads**: Utility bills include both actual meter reads and estimated reads (when the meter couldn't be accessed). An estimated read followed by an actual read creates an adjustment in the next billing period. We don't distinguish estimated from actual.

3. **Sub-metering and net metering**: A site with solar panels generates electricity and may have negative net consumption in some periods. Our parser flags `NEGATIVE_QUANTITY` but a real Scope 2 calculation needs to handle net metering correctly (the exported solar is Scope 2 offset, not a reversal of Scope 2 emissions).

4. **Multi-fuel meters**: Some smart meters track multiple fuel types (electricity + gas) in a single export. Our parser only handles electricity. A gas meter reading would parse the kWh column but produce a wrong emission factor (gas emission factors are per m³, not kWh).

5. **Currency conversion**: We store `bill_amount` but don't use it for emissions. If someone tried to use spend-based Scope 2 accounting (unusual but possible), they'd need current exchange rates.

---

## 3. Corporate Travel Data

### What I researched

**SAP Concur** (used by ~70% of Fortune 500, per Concur's own figures). The platform processes both travel bookings and expense reports. From an ESG perspective, expense reports are the data source because they contain:
- Actual spend (vs booked amounts that may not be travelled)
- Vendor names, departure/arrival cities
- Expense type categorization (Airfare, Hotel, Car Rental, etc.)

The **Analyze** module in Concur allows building custom CSV reports. Standard fields available:
- Report header: Report Name, Employee ID, Employee Name, Department, Cost Center, Submit Date, Approved Date
- Line item: Expense Type, Transaction Date, Vendor Name, City, Country, Currency, Amount (original), Amount (USD), Payment Type
- Travel-specific: Flight From, Flight To, Service Class, Nights, Check-in Date, Check-out Date, Miles

**IATA airport codes**: Concur records origin and destination as 3-letter IATA codes (LHR, JFK). Distances are not stored — the booking system knows the route but the expense report export doesn't carry it. We compute great-circle distances from a coordinate lookup.

**Radiative forcing factor**: DEFRA's flight emission factors include a radiative forcing factor of 1.891×, accounting for the non-CO₂ climate effects of aviation (contrails, cirrus cloud formation, NOx at altitude). This is embedded in the published DEFRA figures — we don't apply it separately.

**Class of service multipliers** reflect different seat sizes per DEFRA methodology:
- Economy: baseline
- Business: ~2.9× economy (on long-haul; business class seats occupy roughly 3× the floor space)
- First: ~4× economy

### What the sample data looks like and why

`concur_travel_q1_2024.csv` contains 27 rows covering 5 employees across 7 trips in Q1 2024.

Employee profiles designed to test different scenarios:
- **EMP-0421 (Chen, Operations)**: Two trips — LHR→JFK (long-haul economy) and LHR→LAX (long-haul economy). The LAX trip includes a hotel and rideshare. Tests long-haul distance calculation and multi-row trip aggregation.
- **EMP-0567 (Williams, Sales)**: MAN→CDG (short-haul economy). Tests short-haul distance calculation.
- **EMP-0892 (Patel, Executive)**: LHR→SIN and LHR→JFK in Business class. Both long-haul. Tests the business class multiplier and the significantly higher CO₂e per km. This employee will have the largest individual carbon footprint — a realistic reflection of how executive business travel dominates Scope 3 Category 6.
- **EMP-1034 (Thompson, IT)**: LHR→FRA (short-haul economy). Includes Deutsche Bahn (train) — tests ground transport.
- **EMP-0234 (Ahmed, Admin)**: MAN→BCN (short-haul economy). Low-cost carrier (Ryanair). Tests that low-cost carrier names parse correctly.

Singapore Airlines, British Airways, easyJet, Ryanair, American Airlines, United Airlines — real carrier names as they appear in Concur expense reports.

Currency variation: GBP, EUR, USD, SGD all appear. The `Amount USD` column (Concur's converted amount) is what we use for spend-based fallback calculations.

### What would break in a real deployment

1. **Airport code not in our lookup table**: Our coordinate table covers ~50 major hubs. A route like Manchester (MAN) → Newcastle (NCL) or any second-tier airport would return no distance, triggering `MISSING_EMISSION_FACTOR` or a spend-based fallback. In production, we'd need a complete IATA database (~10,000 airports).

2. **Missing or inconsistent expense type mapping**: Concur lets companies define custom expense types. A client with "Air Travel - Domestic" instead of "Airfare" would not be mapped. We'd need a client-specific EXPENSE_TYPE_MAP configuration in DataSource.config.

3. **Missing Flight From / Flight To columns**: The Analyze report builder is customizable. If the client's report template doesn't include these fields, we can't compute distance. All flights would fall back to spend-based estimation.

4. **Approved vs submitted expenses**: We assume uploaded expense reports contain only approved expenses. If a client uploads submitted-but-pending reports, we'd ingest costs that may later be rejected. The prototype doesn't filter by report status.

5. **Shared costs and split expenses**: When a manager books a hotel for their team, the cost may appear on one report. We count it as one person's travel. Team travel is genuinely hard to allocate correctly from expense data.
