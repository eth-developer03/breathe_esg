"""
SAP MB51 flat-file parser.

Format: Tab-delimited export from SAP transaction MB51 (Material Document List).
MB51 is the standard way facilities managers pull material movement data without
SAP Basis involvement. The file comes from SAP's List Viewer (ALV) export
function, which produces a .txt or .xlsx file with SAP-internal column headers.

On German-language SAP systems (common in European enterprises), column headers
appear in German. We map both German and English variants.

Relevant SAP tables:
  MSEG — material document segment (one row per material, per movement)
  MKPF — material document header (date, plant, user)

Movement types we care about (Scope 1 fuels):
  201 — Goods issue to cost center (direct consumption, most fuel)
  261 — Goods issue for production order
  291 — Goods issue for network activity
  501 — Receipt without purchase order
  We exclude 102/202 (reversals) unless quantity is positive.

SAP unit codes:
  L   → litres
  M3  → cubic metres (gas)
  KG  → kilograms
  STK → pieces (Stück) — skip for emissions
  GJ  → gigajoules
"""

import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Iterator, Dict, Any


# Map SAP/German column names to our normalized internal names
COLUMN_MAP = {
    # German header → internal
    'Buchungsdatum': 'posting_date',
    'Belegdatum': 'document_date',
    'Werk': 'plant',
    'Material': 'material_number',
    'Materialkurztext': 'material_description',
    'Menge': 'quantity',
    'ME': 'unit',
    'Bwart': 'movement_type',
    'Bewegungsart': 'movement_type',
    'Lieferant': 'vendor',
    'Einkaufsbelegnr.': 'po_number',
    'Kostenstelle': 'cost_center',
    'Belegjahr': 'document_year',
    'Belegnr.': 'document_number',
    'Pos': 'line_item',
    # English header variants (some SAP systems)
    'Posting Date': 'posting_date',
    'Document Date': 'document_date',
    'Plant': 'plant',
    'Material': 'material_number',
    'Material Description': 'material_description',
    'Quantity': 'quantity',
    'Base Unit of Measure': 'unit',
    'Movement Type': 'movement_type',
    'Vendor': 'vendor',
}

# SAP unit codes → canonical unit (we normalise everything to litres for liquid fuels,
# cubic metres for gas, kg for solid fuels)
UNIT_CONVERSION = {
    'L': ('L', Decimal('1')),
    'LT': ('L', Decimal('1')),         # alternate SAP code
    'M3': ('m³', Decimal('1')),
    'KG': ('kg', Decimal('1')),
    'GJ': ('GJ', Decimal('1')),
    'T': ('kg', Decimal('1000')),      # metric tonnes → kg
    'G': ('kg', Decimal('0.001')),     # grams → kg
    'GAL': ('L', Decimal('3.78541')),  # US gallons → litres
    'GL': ('L', Decimal('3.78541')),   # alternate SAP code for gallon
}

# SAP material patterns that indicate fuel (used to filter non-fuel procurement rows)
FUEL_MATERIAL_KEYWORDS = [
    'diesel', 'petrol', 'benzin', 'gasoline', 'kraftstoff', 'fuel',
    'erdgas', 'natural gas', 'lpg', 'fluessiggas', 'heizol', 'heating oil',
    'kerosin', 'kerosene', 'nafta', 'propan', 'butan',
]


def _is_fuel_material(description: str) -> bool:
    desc_lower = description.lower()
    return any(kw in desc_lower for kw in FUEL_MATERIAL_KEYWORDS)


def _parse_sap_date(value: str) -> datetime | None:
    """
    SAP exports dates in DD.MM.YYYY (German format) or YYYYMMDD (internal).
    Some ALV exports also produce MM/DD/YYYY if locale is set to English.
    """
    value = value.strip()
    for fmt in ('%d.%m.%Y', '%Y%m%d', '%m/%d/%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _parse_sap_quantity(value: str) -> Decimal | None:
    """
    SAP quantity fields use German number format: 1.234,567 (dot as thousands
    separator, comma as decimal). We strip dots then replace comma with period.
    """
    value = value.strip()
    if not value:
        return None
    # German format: remove thousands separator, swap decimal separator
    value = value.replace('.', '').replace(',', '.')
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _map_headers(headers: list[str]) -> dict[str, int]:
    """Return {internal_name: column_index} for recognised columns."""
    mapping = {}
    for i, h in enumerate(headers):
        h_stripped = h.strip()
        if h_stripped in COLUMN_MAP:
            internal = COLUMN_MAP[h_stripped]
            mapping[internal] = i
    return mapping


def parse(file_content: bytes) -> Iterator[Dict[str, Any]]:
    """
    Yield one dict per data row. Each dict has:
      row_number, raw_data, parsed (or None), error (or None)
    """
    try:
        text = file_content.decode('utf-8')
    except UnicodeDecodeError:
        text = file_content.decode('latin-1')  # SAP sometimes exports in ISO-8859-1

    reader = csv.reader(io.StringIO(text), delimiter='\t')
    rows = list(reader)
    if not rows:
        return

    header_row = rows[0]
    col_map = _map_headers(header_row)

    required = {'posting_date', 'plant', 'material_number', 'quantity', 'unit'}
    missing = required - set(col_map.keys())
    if missing:
        yield {
            'row_number': 0,
            'raw_data': {},
            'parsed': None,
            'error': f"Missing required columns: {', '.join(missing)}. "
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

        date_str = get(row, 'posting_date')
        qty_str = get(row, 'quantity')
        unit_str = get(row, 'unit')
        plant = get(row, 'plant')
        material = get(row, 'material_number')
        description = get(row, 'material_description')
        movement_type = get(row, 'movement_type')
        vendor = get(row, 'vendor')

        date = _parse_sap_date(date_str)
        if date is None:
            yield {'row_number': row_num, 'raw_data': raw_data, 'parsed': None,
                   'error': f"Unparseable date: '{date_str}'"}
            continue

        qty = _parse_sap_quantity(qty_str)
        if qty is None:
            yield {'row_number': row_num, 'raw_data': raw_data, 'parsed': None,
                   'error': f"Unparseable quantity: '{qty_str}'"}
            continue

        if unit_str not in UNIT_CONVERSION:
            yield {'row_number': row_num, 'raw_data': raw_data, 'parsed': None,
                   'error': f"Unknown SAP unit code: '{unit_str}'. "
                            f"Expected one of: {', '.join(UNIT_CONVERSION)}"}
            continue

        canonical_unit, conversion_factor = UNIT_CONVERSION[unit_str]
        normalized_qty = qty * conversion_factor

        yield {
            'row_number': row_num,
            'raw_data': raw_data,
            'error': None,
            'parsed': {
                'posting_date': date.date(),
                'plant': plant,
                'material_number': material,
                'material_description': description,
                'raw_quantity': qty,
                'raw_unit': unit_str,
                'normalized_quantity': normalized_qty,
                'normalized_unit': canonical_unit,
                'movement_type': movement_type,
                'vendor': vendor,
                'is_fuel': _is_fuel_material(description),
            }
        }
