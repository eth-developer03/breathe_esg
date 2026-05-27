from django.contrib import admin
from .models import NormalizedRecord, EmissionFactor, AuditEvent


@admin.register(EmissionFactor)
class EmissionFactorAdmin(admin.ModelAdmin):
    list_display = ['category', 'scope', 'factor_kg_co2e_per_unit', 'unit', 'source', 'year']
    list_filter = ['scope', 'year']
    search_fields = ['category']


@admin.register(NormalizedRecord)
class NormalizedRecordAdmin(admin.ModelAdmin):
    list_display = ['org', 'scope', 'category', 'activity_date', 'facility_code',
                    'normalized_quantity', 'normalized_unit', 'co2e_kg', 'status']
    list_filter = ['status', 'scope', 'source_type', 'category', 'org']
    search_fields = ['facility_code', 'facility_name', 'vendor', 'description']
    readonly_fields = ['raw_record', 'original_values', 'created_at', 'updated_at']
    date_hierarchy = 'activity_date'


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ['event_type', 'user', 'org', 'timestamp']
    list_filter = ['event_type', 'org']
    readonly_fields = ['before_state', 'after_state', 'timestamp']
    # Audit log is append-only — no add/change permissions in admin
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
