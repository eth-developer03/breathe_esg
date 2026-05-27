from rest_framework import serializers
from .models import NormalizedRecord, EmissionFactor, AuditEvent


class EmissionFactorSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmissionFactor
        fields = ['id', 'category', 'scope', 'factor_kg_co2e_per_unit', 'unit', 'source', 'year']


class NormalizedRecordSerializer(serializers.ModelSerializer):
    scope_display = serializers.CharField(source='get_scope_display', read_only=True)
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    reviewed_by_name = serializers.SerializerMethodField()
    emission_factor_display = serializers.SerializerMethodField()
    raw_row_number = serializers.SerializerMethodField()

    class Meta:
        model = NormalizedRecord
        fields = [
            'id', 'source_type', 'scope', 'scope_display', 'category', 'category_display',
            'activity_date', 'period_start', 'period_end',
            'facility_code', 'facility_name', 'country',
            'raw_quantity', 'raw_unit', 'normalized_quantity', 'normalized_unit',
            'vendor', 'description',
            'emission_factor_display', 'co2e_kg',
            'was_edited', 'original_values',
            'status', 'status_display', 'flags',
            'reviewed_by_name', 'reviewed_at', 'review_notes',
            'created_at', 'updated_at',
            'raw_row_number',
        ]
        read_only_fields = [
            'id', 'source_type', 'scope', 'category', 'raw_quantity', 'raw_unit',
            'original_values', 'was_edited', 'created_at', 'raw_row_number',
            'reviewed_by_name', 'reviewed_at',
        ]

    def get_reviewed_by_name(self, obj):
        if obj.reviewed_by:
            return obj.reviewed_by.get_full_name() or obj.reviewed_by.username
        return None

    def get_emission_factor_display(self, obj):
        if obj.emission_factor:
            return {
                'category': obj.emission_factor.category,
                'factor': str(obj.emission_factor.factor_kg_co2e_per_unit),
                'unit': obj.emission_factor.unit,
                'source': obj.emission_factor.source,
                'year': obj.emission_factor.year,
            }
        return None

    def get_raw_row_number(self, obj):
        if obj.raw_record:
            return obj.raw_record.source_row_number
        return None


class RecordEditSerializer(serializers.ModelSerializer):
    """Used for analyst edits — only editable fields, enforces reason."""
    reason = serializers.CharField(write_only=True, required=True, min_length=5)

    class Meta:
        model = NormalizedRecord
        fields = [
            'normalized_quantity', 'normalized_unit', 'facility_name',
            'vendor', 'description', 'country', 'review_notes', 'reason',
        ]

    def validate_normalized_quantity(self, value):
        if value < 0:
            raise serializers.ValidationError("Quantity cannot be negative.")
        return value


class AuditEventSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    event_type_display = serializers.CharField(source='get_event_type_display', read_only=True)

    class Meta:
        model = AuditEvent
        fields = ['id', 'event_type', 'event_type_display', 'user_name', 'before_state',
                  'after_state', 'notes', 'timestamp']

    def get_user_name(self, obj):
        if obj.user:
            return obj.user.get_full_name() or obj.user.username
        return 'System'
