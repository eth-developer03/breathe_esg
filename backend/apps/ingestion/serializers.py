from rest_framework import serializers
from .models import DataSource, ImportBatch, RawRecord


class DataSourceSerializer(serializers.ModelSerializer):
    source_type_display = serializers.CharField(source='get_source_type_display', read_only=True)

    class Meta:
        model = DataSource
        fields = ['id', 'name', 'source_type', 'source_type_display', 'description', 'config', 'created_at']
        read_only_fields = ['id', 'created_at']


class ImportBatchSerializer(serializers.ModelSerializer):
    source_name = serializers.CharField(source='source.name', read_only=True)
    source_type = serializers.CharField(source='source.source_type', read_only=True)
    uploaded_by_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = ImportBatch
        fields = [
            'id', 'source_name', 'source_type', 'status', 'status_display',
            'file_name', 'uploaded_by_name', 'started_at', 'completed_at',
            'total_rows', 'success_rows', 'error_rows', 'warning_rows', 'error_details',
        ]

    def get_uploaded_by_name(self, obj):
        if obj.uploaded_by:
            return obj.uploaded_by.get_full_name() or obj.uploaded_by.username
        return None
