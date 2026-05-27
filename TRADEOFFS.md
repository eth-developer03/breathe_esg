# Tradeoffs

Three things I deliberately did not build and why.

---

## 1. Real-time SAP connection via RFC / OData

**What this would look like:** A Django management command (or scheduled Celery task) that connects directly to SAP via an RFC (Remote Function Call) or the OData API, pulls MB51 data on a schedule, and ingests it automatically. No file upload required.

**Why I didn't build it:**
This would require: (a) the SAP system to be network-accessible from our server, (b) valid SAP credentials (service account), (c) SAP RFC libraries (`pyrfc`, which requires the proprietary SAP NetWeaver RFC SDK, which is not freely distributable), and (d) the client's BASIS team to configure an outbound RFC destination.

In a real deployment, this setup takes 2-4 weeks of IT coordination and involves the client's CISO. It's an excellent target for a Phase 2, but the file-upload approach gets analysts working in day one without any SAP IT involvement.

The data model is designed to accommodate this: `DataSource.config` can store RFC connection parameters, and the parser can be swapped for an RFC-based puller without changing the NormalizedRecord structure downstream.

**The cost:** Manual upload workflow. The analyst must remember to export and upload each period. This creates a process dependency that a real client would want to automate. Tracked as a known gap.

---

## 2. Market-based Scope 2 accounting (REGOs / PPAs)

**What this would look like:** An additional `EmissionFactor` per meter linked to renewable energy certificates (REGOs in the UK, RECs in the US) or Power Purchase Agreements. A `scope_2_accounting_method` field on NormalizedRecord (`location_based` | `market_based`). The approved CO₂e figure would switch based on the method selected for the reporting period.

**Why I didn't build it:**
Market-based Scope 2 requires certificate data: the client needs to supply REGO certificate numbers, volumes, and validity periods, which are tracked in a separate system (e.g., Ofgem's REGO database). Without that data, we can't calculate a market-based figure correctly.

The GHG Protocol requires companies to report both methods if they use market-based. Implementing one half of the calculation without the certificate data layer would produce misleading output.

The current implementation calculates location-based Scope 2 only, which is always correct with the data we have. When the client can supply certificate data, the `EmissionFactor` table's category and the per-meter config in `DataSource` can be extended without changing the core NormalizedRecord model.

**The cost:** Clients who have signed PPAs or hold REGOs cannot claim their renewable electricity benefit in this prototype. This matters — a UK client with 100% renewable tariff could have near-zero Scope 2, but we'd report the UK grid average. This is a significant gap for real ESG reporting.

---

## 3. Automated statistical outlier detection via time-series model

**What this would look like:** A per-facility, per-category time-series model (ARIMA or seasonal decomposition) that establishes a usage baseline and confidence interval. Records outside the interval get flagged as `STATISTICAL_OUTLIER` with a predicted range shown to the analyst. The model retrained monthly.

**Why I didn't build it:**
The prototype currently uses a simpler heuristic: flag if the value is > 3× the trailing 6-month average for the same facility and category. This works for obvious anomalies but has two problems:
1. It doesn't account for seasonality. A factory that uses 3× more electricity in summer (air conditioning) would be flagged every summer even though the pattern is normal. A proper time-series model handles this.
2. A new meter or plant has no history, so the heuristic never fires.

Building a proper time-series model requires: enough historical data (at least 12+ months) to train on, a scheduled retraining job (Celery Beat), and a way to persist model artefacts (an ML model store or just pickle files in blob storage).

For a prototype with fabricated Q1 2024 data, there's insufficient history to make a time-series model meaningful. The simple 3× heuristic catches the most obvious data quality issues and flags them for analyst review. When the client has been on the platform for 12+ months, upgrading the outlier detection is a well-defined ML feature.

**The cost:** False positives (normal seasonal variation flagged as outlier) and false negatives (a consistent but wrong reading that the 3× threshold misses). Analysts will need to use judgment on flagged records rather than relying purely on the system's assessment.
