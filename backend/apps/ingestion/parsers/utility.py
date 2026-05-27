"""
Utility electricity CSV parser — Green Button-inspired portal export format.

Format rationale: Most US utilities (PG&E, National Grid, Con Edison, Duke Energy)
and major UK utilities (British Gas, EDF, E.ON) offer CSV downloads from their
customer portals. The Green Button standard (ANSI/NAESB REQ.21) is the most
widely adopted template, used by ~60% of US utilities and an increasing number
of international ones.

We chose CSV over:
  PDF — brittle, varies by utility, requires OCR for older bills
  API — Green Button Connect (ESPI protocol) exists but requires OAuth setup
        per utility; most enterprise clients don't have it configured
  EDI 867 — used by large commercial/industrial accounts but not consumer portals

Key realities of utility data that we handle:
  1. Billing periods do NOT align to calendar months. A December bill might cover
     Nov 18 – Dec 19. We store period_start / period_end separately from
     activity_date (which we set to period_end for sorting purposes).
  2. kW vs kWh distinction matters. kW is peak demand (instantaneous); kWh is
     consumption (what we need for emissions). Some exports include both.
  3. Multi-meter accounts: one account may have several meters (sub-meters per
     floor, HVAC sub-metering). We normalise per meter.
  4. Rate schedule codes are cryptic but relevant. "I-6 TOU" vs "E-19" imply
     different tariff structures that may affect scope 2 market-based accounting.
"""

import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Iterator, Dict, Any


# Column name variants across different utility portal exports
COLUMN_MAP = {
    # Canonical / Green Button-style
    'Account Number': 'account_number',
    'Account No': 'account_number',
    'Meter ID': 'meter_id',
    'Meter Number': 'meter_id',
    'Meter Serial': 'meter_id',
    'Service Address': 'service_address',
    'Address': 'service_address',
    'Billing Period Start': 'period_start',
    'Start Date': 'period_start',
    'From Date': 'period_start',
    'Billing Period End': 'period_end',
    'End Date': 'period_end',
    'To Date': 'period_end',
    'Read Date': 'period_end',
    'Consumption (kWh)': 'consumption_kwh',
    'Usage (kWh)': 'consumption_kwh',
    'Total Usage': 'consumption_kwh',
    'kWh': 'consumption_kwh',
    'Net Usage (kWh)': 'consumption_kwh',
    'Peak Demand (kW)': 'peak_demand_kw',
    'Demand (kW)': 'peak_demand_kw',
    'Max Demand': 'peak_demand_kw',
    'Rate Schedule': 'rate_schedule',
    'Tariff': 'rate_schedule',
    'Rate Code': 'rate_schedule',
    'Bill Amount (USD)': 'bill_amount',
    'Amount Due': 'bill_amount',
    'Total Charges': 'bill_amount',
    'Charges ($)': 'bill_amount',
    'Currency': 'currency',
    'Country': 'country',
    'Utility Name': 'utility_name',
    'Supplier': 'utility_name',
}


def _parse_date(value: str) -> datetime | None:
    value = value.strip()
    for fmt in ('%m/%d/%Y', '%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%m-%d-%Y',
                '%d.%m.%Y', '%Y/%m/%d'):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _parse_decimal(value: str) -> Decimal | None:
    value = value.strip().replace(',', '').replace('$', '').replace('£', '').replace('€', '')
    if not value or value == '-':
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _map_headers(headers: list[str]) -> dict[str, int]:
    mapping = {}
    for i, h in enumerate(headers):
        h_stripped = h.strip()
        if h_stripped in COLUMN_MAP:
            mapping[COLUMN_MAP[h_stripped]] = i
    return mapping


def parse(file_content: bytes) -> Iterator[Dict[str, Any]]:
    try:
        text = file_content.decode('utf-8')
    except UnicodeDecodeError:
        text = file_content.decode('latin-1')

    # Skip any preamble lines (utility portals sometimes add account info before the table)
    lines = text.splitlines()
    header_line_idx = 0
    for i, line in enumerate(lines):
        if 'kWh' in line or 'Consumption' in line or 'Usage' in line or 'Account' in line:
            header_line_idx = i
            break

    csv_text = '\n'.join(lines[header_line_idx:])
    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)
    if not rows:
        return

    header_row = rows[0]
    col_map = _map_headers(header_row)

    if 'consumption_kwh' not in col_map:
        yield {
            'row_number': 0,
            'raw_data': {},
            'parsed': None,
            'error': f"Could not find consumption column. "
                     f"Expected one of: 'Consumption (kWh)', 'Usage (kWh)', 'kWh'. "
                     f"Found columns: {', '.join(h.strip() for h in header_row)}"
        }
        return

    def get(row, key):
        idx = col_map.get(key)
        return row[idx].strip() if idx is not None and idx < len(row) else ''

    for row_num, row in enumerate(rows[1:], start=2):
        if not any(cell.strip() for cell in row):
            continue

        raw_data = {h.strip(): row[i] if i < len(row) else '' for i, h in enumerate(header_row)}

        period_end_str = get(row, 'period_end')
        period_start_str = get(row, 'period_start')
        kwh_str = get(row, 'consumption_kwh')

        period_end = _parse_date(period_end_str) if period_end_str else None
        period_start = _parse_date(period_start_str) if period_start_str else None

        if period_end is None and period_start is None:
            yield {'row_number': row_num, 'raw_data': raw_data, 'parsed': None,
                   'error': f"No parseable date found in '{period_end_str}' / '{period_start_str}'"}
            continue

        kwh = _parse_decimal(kwh_str)
        if kwh is None:
            yield {'row_number': row_num, 'raw_data': raw_data, 'parsed': None,
                   'error': f"Unparseable consumption value: '{kwh_str}'"}
            continue

        demand_kw = _parse_decimal(get(row, 'peak_demand_kw'))
        bill_amount = _parse_decimal(get(row, 'bill_amount'))

        # activity_date is the end of the billing period (standard for attribution)
        activity_date = (period_end or period_start).date()

        yield {
            'row_number': row_num,
            'raw_data': raw_data,
            'error': None,
            'parsed': {
                'account_number': get(row, 'account_number'),
                'meter_id': get(row, 'meter_id'),
                'service_address': get(row, 'service_address'),
                'period_start': period_start.date() if period_start else None,
                'period_end': period_end.date() if period_end else None,
                'activity_date': activity_date,
                'consumption_kwh': kwh,
                'peak_demand_kw': demand_kw,
                'rate_schedule': get(row, 'rate_schedule'),
                'bill_amount': bill_amount,
                'currency': get(row, 'currency') or 'USD',
                'utility_name': get(row, 'utility_name'),
                'country': get(row, 'country'),
            }
        }
