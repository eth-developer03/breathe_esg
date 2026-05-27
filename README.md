# Breathe ESG — Emissions Data Ingestion & Review Platform

A Django REST + React prototype that ingests emissions activity data from three real-world source types, normalises it, and provides an analyst review dashboard with audit trail.

## Quick Start (Local)

### Prerequisites
- Python 3.12+
- Node 20+
- PostgreSQL 15+

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Create a .env file from the example
cp ../.env.example .env
# Edit .env with your DB credentials

# Run migrations and seed demo data
python manage.py migrate
python manage.py seed_demo

# Start dev server
python manage.py runserver
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

**Demo credentials:**
- `analyst` / `analyst123` — can review and approve records
- `admin` / `admin123` — full access + Django admin at /admin/

### Upload sample data

1. Log in as analyst
2. Go to Upload
3. Select "SAP MB51 — Fuel Movements", upload `sample_data/sap_mb51_fuel_q1_2024.txt`
4. Select "National Grid — Electricity Portal Export", upload `sample_data/utility_electricity_q1_2024.csv`
5. Select "Concur — Expense Report Export", upload `sample_data/concur_travel_q1_2024.csv`
6. Go to Review to see normalised records with quality flags

## Architecture

```
backend/
├── apps/core/         # Organization, membership
├── apps/ingestion/    # DataSource, ImportBatch, RawRecord, parsers
│   └── parsers/       # sap.py, utility.py, travel.py
└── apps/emissions/    # NormalizedRecord, EmissionFactor, AuditEvent

frontend/
└── src/
    ├── pages/         # Dashboard, Upload, Review, Login
    ├── components/    # Layout, RecordDrawer
    └── api/           # Typed API client
```

## Key design documents

- [MODEL.md](MODEL.md) — data model rationale
- [DECISIONS.md](DECISIONS.md) — every ambiguity resolved
- [TRADEOFFS.md](TRADEOFFS.md) — what was deliberately not built
- [SOURCES.md](SOURCES.md) — source format research

## Deployment (Render)

1. Push to GitHub
2. Connect repo to Render
3. Render reads `render.yaml` — creates backend (Python web service), frontend (static site), and PostgreSQL database automatically
4. Set `VITE_API_URL` env var on the frontend service to the backend's public URL

## Data Sources

| Source | Format | Parser |
|--------|--------|--------|
| SAP MB51 fuel movements | Tab-delimited flat file, German headers | `parsers/sap.py` |
| Utility electricity | Portal CSV (Green Button format) | `parsers/utility.py` |
| Corporate travel (Concur) | Expense report CSV | `parsers/travel.py` |

## Emission Factors

From DEFRA 2023 GHG Conversion Factors (UK) and EPA eGRID 2022 (US). Stored in the database, versioned by year, loaded via `python manage.py loaddata emission_factors`.
