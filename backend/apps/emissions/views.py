from datetime import date
from django.db.models import Count, Sum, Q
from django.utils import timezone
from rest_framework import generics, filters, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
import django_filters

from apps.core.models import OrganizationMembership
from .models import NormalizedRecord, EmissionFactor, AuditEvent
from .serializers import (
    NormalizedRecordSerializer, RecordEditSerializer,
    EmissionFactorSerializer, AuditEventSerializer
)


def get_user_org(request):
    membership = request.user.memberships.select_related('org').first()
    return membership.org if membership else None


class RecordFilter(django_filters.FilterSet):
    status = django_filters.CharFilter()
    scope = django_filters.NumberFilter()
    source_type = django_filters.CharFilter()
    category = django_filters.CharFilter()
    date_from = django_filters.DateFilter(field_name='activity_date', lookup_expr='gte')
    date_to = django_filters.DateFilter(field_name='activity_date', lookup_expr='lte')
    has_flags = django_filters.BooleanFilter(method='filter_has_flags')
    flag = django_filters.CharFilter(method='filter_flag')

    def filter_has_flags(self, qs, name, value):
        if value:
            return qs.exclude(flags=[])
        return qs.filter(flags=[])

    def filter_flag(self, qs, name, value):
        return qs.filter(flags__contains=[value])

    class Meta:
        model = NormalizedRecord
        fields = ['status', 'scope', 'source_type', 'category']


class NormalizedRecordListView(generics.ListAPIView):
    serializer_class = NormalizedRecordSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = RecordFilter
    search_fields = ['facility_name', 'vendor', 'description', 'facility_code']
    ordering_fields = ['activity_date', 'co2e_kg', 'normalized_quantity', 'created_at']
    ordering = ['-activity_date']

    def get_queryset(self):
        org = get_user_org(self.request)
        return (
            NormalizedRecord.objects
            .filter(org=org)
            .select_related('emission_factor', 'reviewed_by', 'raw_record')
        )


class NormalizedRecordDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method in ('PUT', 'PATCH'):
            return RecordEditSerializer
        return NormalizedRecordSerializer

    def get_queryset(self):
        org = get_user_org(self.request)
        return NormalizedRecord.objects.filter(org=org).select_related(
            'emission_factor', 'reviewed_by', 'raw_record'
        )

    def update(self, request, *args, **kwargs):
        record = self.get_object()
        serializer = RecordEditSerializer(record, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        reason = serializer.validated_data.pop('reason')
        before = NormalizedRecordSerializer(record).data

        # Snapshot original values on first edit
        if not record.was_edited:
            record.original_values = {
                'normalized_quantity': str(record.normalized_quantity),
                'normalized_unit': record.normalized_unit,
                'facility_name': record.facility_name,
                'vendor': record.vendor,
                'description': record.description,
                'country': record.country,
            }
            record.was_edited = True

        for field, value in serializer.validated_data.items():
            setattr(record, field, value)
        record.save()

        AuditEvent.objects.create(
            org=record.org,
            record=record,
            user=request.user,
            event_type=AuditEvent.EVENT_RECORD_EDITED,
            before_state=before,
            after_state=NormalizedRecordSerializer(record).data,
            notes=reason,
            ip_address=request.META.get('REMOTE_ADDR'),
        )

        return Response(NormalizedRecordSerializer(record).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def approve_record(request, pk):
    org = get_user_org(request)
    try:
        record = NormalizedRecord.objects.get(id=pk, org=org)
    except NormalizedRecord.DoesNotExist:
        return Response({'error': 'Not found'}, status=404)

    if record.status == NormalizedRecord.STATUS_APPROVED:
        return Response({'error': 'Already approved'}, status=400)

    before_status = record.status
    record.status = NormalizedRecord.STATUS_APPROVED
    record.reviewed_by = request.user
    record.reviewed_at = timezone.now()
    record.review_notes = request.data.get('notes', '')
    record.save()

    AuditEvent.objects.create(
        org=org,
        record=record,
        user=request.user,
        event_type=AuditEvent.EVENT_RECORD_APPROVED,
        before_state={'status': before_status},
        after_state={'status': NormalizedRecord.STATUS_APPROVED},
        notes=record.review_notes,
        ip_address=request.META.get('REMOTE_ADDR'),
    )

    return Response(NormalizedRecordSerializer(record).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def reject_record(request, pk):
    org = get_user_org(request)
    try:
        record = NormalizedRecord.objects.get(id=pk, org=org)
    except NormalizedRecord.DoesNotExist:
        return Response({'error': 'Not found'}, status=404)

    notes = request.data.get('notes', '')
    if not notes:
        return Response({'error': 'Rejection reason required'}, status=400)

    before_status = record.status
    record.status = NormalizedRecord.STATUS_REJECTED
    record.reviewed_by = request.user
    record.reviewed_at = timezone.now()
    record.review_notes = notes
    record.save()

    AuditEvent.objects.create(
        org=org,
        record=record,
        user=request.user,
        event_type=AuditEvent.EVENT_RECORD_REJECTED,
        before_state={'status': before_status},
        after_state={'status': NormalizedRecord.STATUS_REJECTED},
        notes=notes,
        ip_address=request.META.get('REMOTE_ADDR'),
    )

    return Response(NormalizedRecordSerializer(record).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def bulk_approve(request):
    """Approve multiple records at once. IDs in request body."""
    org = get_user_org(request)
    record_ids = request.data.get('ids', [])
    if not record_ids:
        return Response({'error': 'ids required'}, status=400)

    records = NormalizedRecord.objects.filter(
        id__in=record_ids, org=org,
        status__in=[NormalizedRecord.STATUS_PENDING, NormalizedRecord.STATUS_FLAGGED]
    )

    updated = []
    for record in records:
        record.status = NormalizedRecord.STATUS_APPROVED
        record.reviewed_by = request.user
        record.reviewed_at = timezone.now()
        record.save()
        AuditEvent.objects.create(
            org=org, record=record, user=request.user,
            event_type=AuditEvent.EVENT_RECORD_APPROVED,
            before_state={'status': record.status},
            after_state={'status': NormalizedRecord.STATUS_APPROVED},
            ip_address=request.META.get('REMOTE_ADDR'),
        )
        updated.append(str(record.id))

    return Response({'approved': len(updated), 'ids': updated})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def record_audit_trail(request, pk):
    org = get_user_org(request)
    events = AuditEvent.objects.filter(org=org, record__id=pk).select_related('user')
    return Response(AuditEventSerializer(events, many=True).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_stats(request):
    org = get_user_org(request)
    qs = NormalizedRecord.objects.filter(org=org)

    status_counts = dict(
        qs.values('status').annotate(count=Count('id')).values_list('status', 'count')
    )
    scope_co2 = list(
        qs.filter(status=NormalizedRecord.STATUS_APPROVED)
        .values('scope')
        .annotate(co2e_kg=Sum('co2e_kg'))
        .order_by('scope')
    )
    source_counts = list(
        qs.values('source_type').annotate(count=Count('id'), co2e_kg=Sum('co2e_kg'))
    )
    flag_counts = {}
    for record in qs.exclude(flags=[]):
        for flag in record.flags:
            flag_counts[flag] = flag_counts.get(flag, 0) + 1

    return Response({
        'total_records': qs.count(),
        'status_breakdown': {
            'pending': status_counts.get('PENDING', 0),
            'approved': status_counts.get('APPROVED', 0),
            'rejected': status_counts.get('REJECTED', 0),
            'flagged': status_counts.get('FLAGGED', 0),
        },
        'scope_co2e_kg': scope_co2,
        'source_breakdown': source_counts,
        'flag_breakdown': flag_counts,
        'total_co2e_kg': qs.filter(
            status=NormalizedRecord.STATUS_APPROVED, co2e_kg__isnull=False
        ).aggregate(total=Sum('co2e_kg'))['total'] or 0,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def audit_log(request):
    org = get_user_org(request)
    events = (
        AuditEvent.objects
        .filter(org=org)
        .select_related('user', 'record', 'batch')[:200]
    )
    return Response(AuditEventSerializer(events, many=True).data)
