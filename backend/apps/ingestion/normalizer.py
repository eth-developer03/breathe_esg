"""
Normalizer: converts parser output into NormalizedRecord instances.
Also runs quality flag detection.
"""

from datetime import date, timedelta
from decimal import Decimal
from django.utils import timezone
from apps.emissions.models import NormalizedRecord, EmissionFactor, AuditEvent
from apps.ingestion.models import RawRecord
from apps.core.models import Organization


def _get_emission_factor(category: str, year: int) -> EmissionFactor | None:
    return (
        EmissionFactor.objects
        .filter(category=category, year__lte=year)
        .order_by('-year')
        .first()
    )


def _detect_flags(record_data: dict, org: Organization, category: str) -> list[str]:
    flags = []
    qty = record_data.get('normalized_quantity', Decimal('0'))
    act_date = record_data.get('activity_date')
    today = date.today()

    if qty == 0:
        flags.append('ZERO_QUANTITY')
    elif qty < 0:
        flags.append('NEGATIVE_QUANTITY')

    if act_date:
        if act_date > today:
            flags.append('FUTURE_DATE')
        elif act_date < today - timedelta(days=730):
            flags.append('STALE_DATE')

    facility = record_data.get('facility_code', '')
    if facility and record_data.get('source_type') == 'SAP':
        if facility not in org.plant_lookup and facility:
            flags.append('UNKNOWN_FACILITY')

    if record_data.get('emission_factor') is None:
        flags.append('MISSING_EMISSION_FACTOR')

    # Statistical outlier: flag if quantity is > 3x the recent average for same facility
    recent_avg = _get_recent_average(org, category, facility)
    if recent_avg and recent_avg > 0 and qty > recent_avg * Decimal('3'):
        flags.append('STATISTICAL_OUTLIER')

    # Duplicate candidate: same date, facility, quantity already exists
    if _is_likely_duplicate(org, category, act_date, facility, qty):
        flags.append('DUPLICATE_CANDIDATE')

    return flags


def _get_recent_average(org, category, facility_code, months=6) -> Decimal | None:
    from django.db.models import Avg
    cutoff = date.today() - timedelta(days=months * 30)
    result = (
        NormalizedRecord.objects
        .filter(
            org=org,
            category=category,
            facility_code=facility_code,
            activity_date__gte=cutoff,
            status=NormalizedRecord.STATUS_APPROVED,
        )
        .aggregate(avg=Avg('normalized_quantity'))
    )
    val = result.get('avg')
    return Decimal(str(val)) if val is not None else None


def _is_likely_duplicate(org, category, activity_date, facility_code, quantity) -> bool:
    if not activity_date:
        return False
    return NormalizedRecord.objects.filter(
        org=org,
        category=category,
        activity_date=activity_date,
        facility_code=facility_code,
        normalized_quantity=quantity,
    ).exists()


def normalize_sap_row(parsed: dict, raw_record: RawRecord, org: Organization) -> NormalizedRecord:
    facility_code = parsed['plant']
    facility_name = org.resolve_plant(facility_code)
    category = NormalizedRecord.CATEGORY_FUEL
    activity_date = parsed['posting_date']
    em_factor = _get_emission_factor(
        _sap_emission_category(parsed.get('material_description', '')),
        activity_date.year
    )
    normalized_qty = parsed['normalized_quantity']
    normalized_unit = parsed['normalized_unit']
    co2e = (normalized_qty * em_factor.factor_kg_co2e_per_unit) if em_factor else None

    record_data = {
        'source_type': 'SAP',
        'scope': NormalizedRecord.SCOPE_1,
        'category': category,
        'activity_date': activity_date,
        'facility_code': facility_code,
        'facility_name': facility_name,
        'raw_quantity': parsed['raw_quantity'],
        'raw_unit': parsed['raw_unit'],
        'normalized_quantity': normalized_qty,
        'normalized_unit': normalized_unit,
        'vendor': parsed.get('vendor', ''),
        'description': parsed.get('material_description', ''),
        'emission_factor': em_factor,
        'co2e_kg': co2e,
    }

    flags = _detect_flags(record_data, org, category)

    return NormalizedRecord(
        raw_record=raw_record,
        org=org,
        **record_data,
        flags=flags,
        status=NormalizedRecord.STATUS_FLAGGED if flags else NormalizedRecord.STATUS_PENDING,
    )


def normalize_utility_row(parsed: dict, raw_record: RawRecord, org: Organization) -> NormalizedRecord:
    meter_id = parsed.get('meter_id') or parsed.get('account_number', '')
    facility_name = parsed.get('service_address', '')
    category = NormalizedRecord.CATEGORY_ELECTRICITY
    activity_date = parsed['activity_date']
    em_factor = _get_emission_factor('electricity_uk_grid', activity_date.year)
    normalized_qty = parsed['consumption_kwh']
    co2e = (normalized_qty * em_factor.factor_kg_co2e_per_unit) if em_factor else None

    record_data = {
        'source_type': 'UTILITY',
        'scope': NormalizedRecord.SCOPE_2,
        'category': category,
        'activity_date': activity_date,
        'period_start': parsed.get('period_start'),
        'period_end': parsed.get('period_end'),
        'facility_code': meter_id,
        'facility_name': facility_name,
        'country': parsed.get('country', ''),
        'raw_quantity': normalized_qty,
        'raw_unit': 'kWh',
        'normalized_quantity': normalized_qty,
        'normalized_unit': 'kWh',
        'vendor': parsed.get('utility_name', ''),
        'description': f"Rate schedule: {parsed.get('rate_schedule', 'N/A')}",
        'emission_factor': em_factor,
        'co2e_kg': co2e,
    }

    flags = _detect_flags(record_data, org, category)

    # Period gap detection: flag if there's no record for the previous billing month
    if _has_period_gap(org, meter_id, parsed.get('period_start')):
        flags.append('PERIOD_GAP')

    return NormalizedRecord(
        raw_record=raw_record,
        org=org,
        **record_data,
        flags=flags,
        status=NormalizedRecord.STATUS_FLAGGED if flags else NormalizedRecord.STATUS_PENDING,
    )


def normalize_travel_row(parsed: dict, raw_record: RawRecord, org: Organization) -> NormalizedRecord:
    category_map = {
        'flight': NormalizedRecord.CATEGORY_FLIGHT,
        'hotel': NormalizedRecord.CATEGORY_HOTEL,
        'ground_transport': NormalizedRecord.CATEGORY_GROUND_TRANSPORT,
    }
    category = category_map[parsed['category']]
    activity_date = parsed['transaction_date']
    cost_center = parsed.get('cost_center', '')
    facility_name = org.resolve_cost_center(cost_center) if cost_center else ''

    if parsed['category'] == 'flight':
        distance_km = parsed.get('distance_km')
        if distance_km:
            normalized_qty = Decimal(str(distance_km))
            normalized_unit = 'km'
            em_cat = _flight_emission_category(parsed.get('cabin_class', 'economy'), distance_km)
        else:
            # Fall back to spend-based when distance unknown
            normalized_qty = parsed.get('amount_usd') or Decimal('0')
            normalized_unit = 'USD'
            em_cat = 'flight_economy_medium'
        description = (
            f"{parsed.get('flight_from', '?')} → {parsed.get('flight_to', '?')} "
            f"({parsed.get('cabin_class', 'economy')})"
        )

    elif parsed['category'] == 'hotel':
        nights = parsed.get('nights') or 1
        normalized_qty = Decimal(str(nights))
        normalized_unit = 'nights'
        em_cat = 'hotel_uk'
        description = f"{parsed.get('vendor', '')} — {nights} night(s)"

    else:  # ground_transport
        km = parsed.get('distance_km')
        if km:
            normalized_qty = Decimal(str(km))
            normalized_unit = 'km'
            em_cat = 'car_average_petrol'
        else:
            normalized_qty = parsed.get('amount_usd') or Decimal('0')
            normalized_unit = 'USD'
            em_cat = 'car_average_petrol'
        description = f"{parsed.get('expense_type_raw', '')} — {parsed.get('vendor', '')}"

    em_factor = _get_emission_factor(em_cat, activity_date.year)
    co2e = (normalized_qty * em_factor.factor_kg_co2e_per_unit) if em_factor else None

    record_data = {
        'source_type': 'TRAVEL',
        'scope': NormalizedRecord.SCOPE_3,
        'category': category,
        'activity_date': activity_date,
        'facility_code': cost_center,
        'facility_name': facility_name,
        'country': parsed.get('country', ''),
        'raw_quantity': normalized_qty,
        'raw_unit': normalized_unit,
        'normalized_quantity': normalized_qty,
        'normalized_unit': normalized_unit,
        'vendor': parsed.get('vendor', ''),
        'description': description,
        'emission_factor': em_factor,
        'co2e_kg': co2e,
    }

    flags = _detect_flags(record_data, org, category)

    return NormalizedRecord(
        raw_record=raw_record,
        org=org,
        **record_data,
        flags=flags,
        status=NormalizedRecord.STATUS_FLAGGED if flags else NormalizedRecord.STATUS_PENDING,
    )


def _sap_emission_category(description: str) -> str:
    desc = description.lower()
    if any(k in desc for k in ['diesel', 'gasoil', 'hvb']):
        return 'diesel'
    if any(k in desc for k in ['petrol', 'benzin', 'gasoline']):
        return 'petrol'
    if any(k in desc for k in ['erdgas', 'natural gas', 'methane']):
        return 'natural_gas'
    if any(k in desc for k in ['lpg', 'propan', 'butan', 'fluessiggas']):
        return 'lpg'
    if any(k in desc for k in ['heizol', 'heating oil', 'fuel oil']):
        return 'fuel_oil'
    return 'diesel'  # conservative default


def _flight_emission_category(cabin: str, distance_km: float) -> str:
    is_long_haul = distance_km > 3700
    haul = 'long' if is_long_haul else 'short'
    cabin_clean = cabin.lower()
    if 'business' in cabin_clean:
        return f'flight_business_{haul}'
    if 'first' in cabin_clean:
        return f'flight_first_{haul}'
    return f'flight_economy_{haul}'


def _has_period_gap(org, meter_id: str, period_start) -> bool:
    if not period_start:
        return False
    expected_prior_end = period_start - timedelta(days=1)
    window_start = expected_prior_end - timedelta(days=45)
    return not NormalizedRecord.objects.filter(
        org=org,
        category=NormalizedRecord.CATEGORY_ELECTRICITY,
        facility_code=meter_id,
        period_end__range=(window_start, expected_prior_end),
    ).exists()
