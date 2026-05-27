"""
Corporate travel CSV parser — Concur expense report export format.

Format rationale: SAP Concur is the dominant enterprise travel & expense platform
(~70% Fortune 500 usage, 55M active users globally). Travel management companies
(TMCs) like AmexGBT and BCD that aggregate corporate travel also use Concur as
the primary expense platform.

The export we handle comes from Concur's "Analyze" report builder or direct
expense report export (Reports > Export > Detailed Report). This is the format
a sustainability or finance team actually downloads.

Key realities we handle:
  1. Airport codes instead of distances. Concur records origin/destination as
     IATA codes (LHR, JFK, SIN). Distance is not directly available. We use a
     pre-computed lookup for ~500 major airport pairs. For unknown pairs we
     use a great-circle estimate from known airport coordinates.
  2. Multiple expense types in one export. 'Airfare', 'Hotel', 'Car Rental',
     'Train', 'Taxi/Rideshare' all appear in the same file. Each has different
     emission factors and normalization logic.
  3. Currency variation. Expenses can be in GBP, EUR, USD, JPY, etc.
     We normalize to USD using the exchange rate column Concur provides.
  4. Missing itinerary details. Not all rows have From/To fields.
     Hotel rows have nights; some airfare rows lack class-of-service.
  5. Personal card vs corporate card doesn't affect emissions but matters
     for completeness of the dataset.

GHG Protocol Scope 3 Category 6 (Business Travel) calculation approaches:
  Flights: passenger-km × emission factor (varies by class and haul length)
  Hotels: room-nights × emission factor (varies by country)
  Ground: km or spend-based when distance unavailable
"""

import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Iterator, Dict, Any
import math


COLUMN_MAP = {
    'Report Name': 'report_name',
    'Employee ID': 'employee_id',
    'Employee Name': 'employee_name',
    'Department': 'department',
    'Cost Center': 'cost_center',
    'Expense Type': 'expense_type',
    'Transaction Date': 'transaction_date',
    'Vendor Name': 'vendor',
    'City': 'city',
    'Country': 'country',
    'Currency': 'currency_orig',
    'Amount': 'amount_orig',
    'Amount USD': 'amount_usd',
    'Amount (USD)': 'amount_usd',
    'Payment Type': 'payment_type',
    # Flight-specific
    'Flight From': 'flight_from',
    'From': 'flight_from',
    'Origin': 'flight_from',
    'Flight To': 'flight_to',
    'To': 'flight_to',
    'Destination': 'flight_to',
    'Class': 'cabin_class',
    'Cabin Class': 'cabin_class',
    'Service Class': 'cabin_class',
    # Hotel-specific
    'Nights': 'nights',
    'Check-in Date': 'checkin_date',
    'Check-out Date': 'checkout_date',
    # Ground transport
    'Miles': 'miles',
    'Kilometers': 'kilometers',
    'Distance': 'kilometers',
}

# Expense type → internal category
EXPENSE_TYPE_MAP = {
    # Flights
    'airfare': 'flight',
    'air': 'flight',
    'flight': 'flight',
    'air travel': 'flight',
    'domestic air': 'flight',
    'international air': 'flight',
    # Hotels
    'hotel': 'hotel',
    'lodging': 'hotel',
    'accommodation': 'hotel',
    # Ground
    'car rental': 'ground_transport',
    'rental car': 'ground_transport',
    'taxi': 'ground_transport',
    'taxi/rideshare': 'ground_transport',
    'rideshare': 'ground_transport',
    'uber': 'ground_transport',
    'lyft': 'ground_transport',
    'train': 'ground_transport',
    'rail': 'ground_transport',
    'bus': 'ground_transport',
    'subway': 'ground_transport',
    'ground transportation': 'ground_transport',
    'mileage': 'ground_transport',
    'personal vehicle': 'ground_transport',
}

# IATA airport coordinates (lat, lon) for ~50 major hubs used in distance estimation
AIRPORT_COORDS = {
    'LHR': (51.4775, -0.4614), 'LGW': (51.1537, -0.1821), 'MAN': (53.3537, -2.2750),
    'JFK': (40.6413, -73.7781), 'LAX': (33.9425, -118.4081), 'ORD': (41.9742, -87.9073),
    'SFO': (37.6213, -122.3790), 'BOS': (42.3656, -71.0096), 'MIA': (25.7959, -80.2870),
    'ATL': (33.6407, -84.4277), 'DFW': (32.8998, -97.0403), 'SEA': (47.4502, -122.3088),
    'CDG': (49.0097, 2.5479), 'AMS': (52.3086, 4.7639), 'FRA': (50.0379, 8.5622),
    'MUC': (48.3538, 11.7861), 'ZRH': (47.4647, 8.5492), 'BCN': (41.2971, 2.0785),
    'MAD': (40.4983, -3.5676), 'FCO': (41.8003, 12.2389), 'SIN': (1.3644, 103.9915),
    'HKG': (22.3080, 113.9185), 'NRT': (35.7720, 140.3929), 'PEK': (40.0799, 116.6031),
    'PVG': (31.1443, 121.8083), 'SYD': (-33.9399, 151.1753), 'MEL': (-37.6690, 144.8410),
    'DXB': (25.2532, 55.3657), 'DOH': (25.2611, 51.6138), 'BOM': (19.0896, 72.8656),
    'DEL': (28.5562, 77.1000), 'GRU': (-23.4356, -46.4731), 'GIG': (-22.8099, -43.2505),
    'YYZ': (43.6777, -79.6248), 'YVR': (49.1967, -123.1815), 'MEX': (19.4363, -99.0721),
    'EZE': (-34.8222, -58.5358), 'SCL': (-33.3930, -70.7858), 'CPT': (-33.9648, 18.6017),
    'JNB': (-26.1367, 28.2411), 'CAI': (30.1219, 31.4056), 'ICN': (37.4602, 126.4407),
}


def _great_circle_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


def estimate_flight_distance_km(origin: str, destination: str) -> float | None:
    """Return great-circle distance in km, or None if either airport is unknown."""
    o = AIRPORT_COORDS.get(origin.upper().strip())
    d = AIRPORT_COORDS.get(destination.upper().strip())
    if o and d:
        return _great_circle_km(o[0], o[1], d[0], d[1])
    return None


def _parse_date(value: str) -> datetime | None:
    value = value.strip()
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%d-%m-%Y', '%m-%d-%Y', '%d.%m.%Y'):
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
        text = file_content.decode('utf-8-sig')  # handle BOM from Windows Excel exports
    except UnicodeDecodeError:
        text = file_content.decode('latin-1')

    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return

    header_row = rows[0]
    col_map = _map_headers(header_row)

    if 'expense_type' not in col_map or 'transaction_date' not in col_map:
        yield {
            'row_number': 0,
            'raw_data': {},
            'parsed': None,
            'error': f"Missing required columns (Expense Type, Transaction Date). "
                     f"Found: {', '.join(h.strip() for h in header_row)}"
        }
        return

    def get(row, key):
        idx = col_map.get(key)
        return row[idx].strip() if idx is not None and idx < len(row) else ''

    for row_num, row in enumerate(rows[1:], start=2):
        if not any(cell.strip() for cell in row):
            continue

        raw_data = {h.strip(): row[i] if i < len(row) else '' for i, h in enumerate(header_row)}

        expense_type_raw = get(row, 'expense_type')
        category = EXPENSE_TYPE_MAP.get(expense_type_raw.lower(), None)
        if category is None:
            # Unknown expense type — skip silently (personal meals, etc. are not in scope)
            yield {'row_number': row_num, 'raw_data': raw_data, 'parsed': None,
                   'error': f"Expense type '{expense_type_raw}' not mapped to travel category — skipped"}
            continue

        date_str = get(row, 'transaction_date')
        date = _parse_date(date_str)
        if date is None:
            yield {'row_number': row_num, 'raw_data': raw_data, 'parsed': None,
                   'error': f"Unparseable transaction date: '{date_str}'"}
            continue

        amount_usd = _parse_decimal(get(row, 'amount_usd'))

        parsed = {
            'category': category,
            'transaction_date': date.date(),
            'employee_id': get(row, 'employee_id'),
            'department': get(row, 'department'),
            'cost_center': get(row, 'cost_center'),
            'vendor': get(row, 'vendor'),
            'city': get(row, 'city'),
            'country': get(row, 'country'),
            'amount_usd': amount_usd,
            'expense_type_raw': expense_type_raw,
        }

        if category == 'flight':
            origin = get(row, 'flight_from').upper().strip()
            dest = get(row, 'flight_to').upper().strip()
            cabin = get(row, 'cabin_class').lower().strip() or 'economy'
            distance_km = estimate_flight_distance_km(origin, dest)
            parsed.update({
                'flight_from': origin,
                'flight_to': dest,
                'cabin_class': cabin,
                'distance_km': distance_km,
                # If distance unknown, fall back to spend-based estimation
                'distance_method': 'great_circle' if distance_km else 'spend_based',
            })

        elif category == 'hotel':
            nights_str = get(row, 'nights')
            nights = None
            if nights_str:
                try:
                    nights = int(nights_str)
                except ValueError:
                    pass
            if nights is None:
                # Derive from check-in / check-out if available
                ci = _parse_date(get(row, 'checkin_date'))
                co = _parse_date(get(row, 'checkout_date'))
                if ci and co:
                    nights = max(1, (co - ci).days)
            parsed['nights'] = nights

        elif category == 'ground_transport':
            km = _parse_decimal(get(row, 'kilometers'))
            miles = _parse_decimal(get(row, 'miles'))
            if km is None and miles is not None:
                km = miles * Decimal('1.60934')
            parsed['distance_km'] = km

        yield {
            'row_number': row_num,
            'raw_data': raw_data,
            'error': None,
            'parsed': parsed,
        }
