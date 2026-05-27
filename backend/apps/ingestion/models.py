import uuid
from django.db import models
from django.contrib.auth.models import User
from apps.core.models import Organization


class DataSource(models.Model):
    """
    A configured ingestion source for an org. One source per integration type
    (SAP MB51, utility portal, Concur). Stores config that varies per client
    (SAP plant filter, utility account numbers, Concur report template).
    """
    SOURCE_SAP = 'SAP'
    SOURCE_UTILITY = 'UTILITY'
    SOURCE_TRAVEL = 'TRAVEL'
    SOURCE_CHOICES = [
        (SOURCE_SAP, 'SAP Fuel & Procurement'),
        (SOURCE_UTILITY, 'Utility Electricity'),
        (SOURCE_TRAVEL, 'Corporate Travel'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='sources')
    source_type = models.CharField(max_length=10, choices=SOURCE_CHOICES)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    # config holds source-specific settings:
    # SAP: {"plant_filter": ["1000", "2000"], "movement_types": ["201", "261"]}
    # UTILITY: {"account_numbers": ["ACC-78234"], "utility_name": "National Grid"}
    # TRAVEL: {"cost_centers": ["CC-OPS", "CC-ADMIN"]}
    config = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    class Meta:
        ordering = ['source_type', 'name']

    def __str__(self):
        return f"{self.org.name} — {self.name}"


class ImportBatch(models.Model):
    """
    One file upload = one batch. Tracks parse statistics and preserves the
    original filename. file_hash (SHA-256) lets us warn on re-uploads.
    """
    STATUS_PENDING = 'PENDING'
    STATUS_PROCESSING = 'PROCESSING'
    STATUS_COMPLETED = 'COMPLETED'
    STATUS_FAILED = 'FAILED'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PROCESSING, 'Processing'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_FAILED, 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.ForeignKey(DataSource, on_delete=models.CASCADE, related_name='batches')
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='batches')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default=STATUS_PENDING)
    file_name = models.CharField(max_length=255)
    file_hash = models.CharField(max_length=64, blank=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    total_rows = models.IntegerField(default=0)
    success_rows = models.IntegerField(default=0)
    error_rows = models.IntegerField(default=0)
    warning_rows = models.IntegerField(default=0)
    # Structured parse errors: [{"row": 12, "error": "date format invalid: '32.13.2024'"}]
    error_details = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f"{self.source.name} — {self.file_name} ({self.status})"


class RawRecord(models.Model):
    """
    Immutable snapshot of a single row as it arrived. Never modified after write.
    This is the source-of-truth that auditors can trace back to.
    Analysts reviewing a normalized record can always see what the raw data said.
    """
    PARSE_OK = 'OK'
    PARSE_ERROR = 'ERROR'
    PARSE_SKIPPED = 'SKIPPED'
    PARSE_CHOICES = [
        (PARSE_OK, 'Parsed OK'),
        (PARSE_ERROR, 'Parse Error'),
        (PARSE_SKIPPED, 'Skipped (header/blank)'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name='raw_records')
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='raw_records')
    source_row_number = models.IntegerField()
    # raw_data stores original field names and values, exactly as ingested.
    # For SAP: {"Buchungsdatum": "17.01.2024", "Werk": "1000", "Menge": "5000,000", "ME": "L", ...}
    # For utility: {"Account Number": "ACC-78234", "Consumption (kWh)": "42580", ...}
    # For travel: {"Expense Type": "Airfare", "Amount USD": "1134.45", ...}
    raw_data = models.JSONField()
    parse_status = models.CharField(max_length=10, choices=PARSE_CHOICES, default=PARSE_OK)
    parse_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['batch', 'source_row_number']
        # No updated_at — intentionally immutable

    def __str__(self):
        return f"Row {self.source_row_number} of {self.batch.file_name}"
