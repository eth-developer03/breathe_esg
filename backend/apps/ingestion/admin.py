from django.contrib import admin
from .models import DataSource, ImportBatch, RawRecord


@admin.register(DataSource)
class DataSourceAdmin(admin.ModelAdmin):
    list_display = ['name', 'org', 'source_type', 'created_at']
    list_filter = ['source_type', 'org']


@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    list_display = ['file_name', 'source', 'status', 'total_rows', 'error_rows', 'started_at']
    list_filter = ['status', 'source__source_type']
    readonly_fields = ['file_hash', 'error_details']


@admin.register(RawRecord)
class RawRecordAdmin(admin.ModelAdmin):
    list_display = ['batch', 'source_row_number', 'parse_status', 'created_at']
    list_filter = ['parse_status']
    readonly_fields = ['raw_data', 'created_at']
