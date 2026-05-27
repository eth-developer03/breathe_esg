import uuid
from django.db import models
from django.contrib.auth.models import User
from apps.core.models import Organization
from apps.ingestion.models import RawRecord, ImportBatch


class EmissionFactor(models.Model):
    """
    Emission conversion factors from authoritative sources (DEFRA 2023, EPA, GHG Protocol).
    Versioned by year so historical calculations can be reproduced.
    category is a slugified descriptor: 'diesel', 'electricity_uk_grid', 'flight_economy_short',
    'hotel_uk', 'car_rental_petrol', etc.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    category = models.CharField(max_length=100)
    scope = models.IntegerField(choices=[(1, 'Scope 1'), (2, 'Scope 2'), (3, 'Scope 3')])
    # kg CO2e emitted per one unit of activity
    factor_kg_co2e_per_unit = models.DecimalField(max_digits=12, decimal_places=6)
    unit = models.CharField(max_length=20)  # litre, kWh, km, passenger-km, night
    source = models.CharField(max_length=100)  # e.g. 'DEFRA 2023', 'EPA eGRID 2022'
    year = models.IntegerField()
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ('category', 'year')
        ordering = ['category', '-year']

    def __str__(self):
        return f"{self.category} ({self.year}): {self.factor_kg_co2e_per_unit} kgCO2e/{self.unit}"


class NormalizedRecord(models.Model):
    """
    The analyst-facing, review-ready record derived from a RawRecord.
    Contains normalized values (consistent units, resolved codes) and
    the review workflow state. Can be edited; edits are tracked via
    original_values + AuditEvent.

    Scope classification:
      Scope 1 — SAP fuel movements (diesel, petrol, natural gas, LPG)
      Scope 2 — Utility electricity (market-based or location-based)
      Scope 3 — Corporate travel (Category 6), SAP indirect procurement
    """
    SCOPE_1 = 1
    SCOPE_2 = 2
    SCOPE_3 = 3
    SCOPE_CHOICES = [(1, 'Scope 1'), (2, 'Scope 2'), (3, 'Scope 3')]

    # GHG Protocol Scope 3 categories relevant to this app
    CATEGORY_FUEL = 'fuel'
    CATEGORY_ELECTRICITY = 'electricity'
    CATEGORY_FLIGHT = 'flight'
    CATEGORY_HOTEL = 'hotel'
    CATEGORY_GROUND_TRANSPORT = 'ground_transport'
    CATEGORY_PROCUREMENT = 'procurement'
    CATEGORY_CHOICES = [
        (CATEGORY_FUEL, 'Fuel Combustion'),
        (CATEGORY_ELECTRICITY, 'Purchased Electricity'),
        (CATEGORY_FLIGHT, 'Business Travel — Flight'),
        (CATEGORY_HOTEL, 'Business Travel — Hotel'),
        (CATEGORY_GROUND_TRANSPORT, 'Business Travel — Ground Transport'),
        (CATEGORY_PROCUREMENT, 'Procurement (goods/services)'),
    ]

    STATUS_PENDING = 'PENDING'
    STATUS_APPROVED = 'APPROVED'
    STATUS_REJECTED = 'REJECTED'
    STATUS_FLAGGED = 'FLAGGED'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending Review'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_FLAGGED, 'Flagged for Investigation'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    raw_record = models.OneToOneField(
        RawRecord, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='normalized'
    )
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='records')
    source_type = models.CharField(max_length=10)  # SAP / UTILITY / TRAVEL
    scope = models.IntegerField(choices=SCOPE_CHOICES)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES)

    # Activity period. activity_date is the canonical single date for sorting/grouping.
    # For utility billing (which spans periods), period_start/end capture the actual window.
    activity_date = models.DateField()
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)

    # Facility context. facility_code is the raw code (plant, meter ID, cost center).
    # facility_name is resolved via org lookup tables or left as the code if unknown.
    facility_code = models.CharField(max_length=100, blank=True)
    facility_name = models.CharField(max_length=255, blank=True)
    country = models.CharField(max_length=2, blank=True)  # ISO 3166-1 alpha-2

    # Quantity as ingested (original number + original unit string)
    raw_quantity = models.DecimalField(max_digits=16, decimal_places=4)
    raw_unit = models.CharField(max_length=30)

    # Quantity after unit normalization to the canonical unit for this category:
    #   fuel → litres (L)
    #   electricity → kilowatt-hours (kWh)
    #   flight → passenger-km (pkm) — estimated from airport codes when distance not provided
    #   hotel → nights
    #   ground_transport → km
    #   procurement → USD (spend-based)
    normalized_quantity = models.DecimalField(max_digits=16, decimal_places=4)
    normalized_unit = models.CharField(max_length=20)

    vendor = models.CharField(max_length=255, blank=True)
    description = models.CharField(max_length=500, blank=True)

    # Emission calculation. emission_factor may be null if no factor is mapped yet
    # (triggers MISSING_EMISSION_FACTOR flag). co2e_kg is null until factor is available.
    emission_factor = models.ForeignKey(
        EmissionFactor, on_delete=models.SET_NULL, null=True, blank=True
    )
    co2e_kg = models.DecimalField(max_digits=16, decimal_places=4, null=True, blank=True)

    # Edit tracking: when an analyst changes a field, we snapshot the pre-edit state
    # here. Combined with AuditEvent this gives a full trail. Null means unedited.
    original_values = models.JSONField(null=True, blank=True)
    was_edited = models.BooleanField(default=False)

    # Review workflow
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    # Quality flags detected at normalization time. Stored as a list of string codes.
    # Codes: ZERO_QUANTITY, NEGATIVE_QUANTITY, FUTURE_DATE, STALE_DATE,
    #        UNKNOWN_FACILITY, UNIT_ANOMALY, STATISTICAL_OUTLIER,
    #        MISSING_EMISSION_FACTOR, DUPLICATE_CANDIDATE, PERIOD_GAP
    flags = models.JSONField(default=list)
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_records'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-activity_date', 'facility_code']
        indexes = [
            models.Index(fields=['org', 'status']),
            models.Index(fields=['org', 'scope', 'activity_date']),
            models.Index(fields=['org', 'source_type', 'activity_date']),
        ]

    def __str__(self):
        return f"{self.get_scope_display()} / {self.category} — {self.activity_date} ({self.status})"


class AuditEvent(models.Model):
    """
    Append-only audit log. Never updated or deleted. Records every state change
    that matters for the audit trail: uploads, approvals, rejections, field edits.
    before_state / after_state are JSON snapshots of relevant fields.
    """
    EVENT_BATCH_UPLOADED = 'BATCH_UPLOADED'
    EVENT_BATCH_FAILED = 'BATCH_FAILED'
    EVENT_RECORD_APPROVED = 'RECORD_APPROVED'
    EVENT_RECORD_REJECTED = 'RECORD_REJECTED'
    EVENT_RECORD_FLAGGED = 'RECORD_FLAGGED'
    EVENT_RECORD_EDITED = 'RECORD_EDITED'
    EVENT_RECORD_REOPENED = 'RECORD_REOPENED'
    EVENT_CHOICES = [
        (EVENT_BATCH_UPLOADED, 'Batch Uploaded'),
        (EVENT_BATCH_FAILED, 'Batch Failed'),
        (EVENT_RECORD_APPROVED, 'Record Approved'),
        (EVENT_RECORD_REJECTED, 'Record Rejected'),
        (EVENT_RECORD_FLAGGED, 'Record Flagged'),
        (EVENT_RECORD_EDITED, 'Record Edited'),
        (EVENT_RECORD_REOPENED, 'Record Reopened'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='audit_events')
    record = models.ForeignKey(
        NormalizedRecord, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='audit_events'
    )
    batch = models.ForeignKey(
        ImportBatch, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='audit_events'
    )
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    event_type = models.CharField(max_length=30, choices=EVENT_CHOICES)
    before_state = models.JSONField(default=dict)
    after_state = models.JSONField(default=dict)
    notes = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ['-timestamp']
        # No update fields — intentionally append-only

    def __str__(self):
        return f"{self.event_type} by {self.user} at {self.timestamp}"
