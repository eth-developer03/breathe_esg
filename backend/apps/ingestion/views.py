import hashlib
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db import transaction

from apps.core.models import Organization, OrganizationMembership
from apps.emissions.models import NormalizedRecord, AuditEvent
from .models import DataSource, ImportBatch, RawRecord
from .serializers import DataSourceSerializer, ImportBatchSerializer
from .parsers import sap as sap_parser, utility as utility_parser, travel as travel_parser
from .normalizer import normalize_sap_row, normalize_utility_row, normalize_travel_row


def get_user_org(request):
    membership = request.user.memberships.select_related('org').first()
    if not membership:
        return None
    return membership.org


class DataSourceListCreateView(generics.ListCreateAPIView):
    serializer_class = DataSourceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        org = get_user_org(self.request)
        return DataSource.objects.filter(org=org)

    def perform_create(self, serializer):
        org = get_user_org(self.request)
        serializer.save(org=org, created_by=self.request.user)


class ImportBatchListView(generics.ListAPIView):
    serializer_class = ImportBatchSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['source', 'status']
    ordering_fields = ['started_at', 'total_rows']

    def get_queryset(self):
        org = get_user_org(self.request)
        return ImportBatch.objects.filter(org=org).select_related('source', 'uploaded_by')


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_file(request):
    """
    Accept a file upload and a source_id. Runs the appropriate parser,
    creates RawRecords, then normalizes to NormalizedRecords.
    Returns batch summary with row counts and any parse errors.
    """
    org = get_user_org(request)
    if not org:
        return Response({'error': 'User has no organization'}, status=400)

    source_id = request.data.get('source_id')
    if not source_id:
        return Response({'error': 'source_id required'}, status=400)

    try:
        source = DataSource.objects.get(id=source_id, org=org)
    except DataSource.DoesNotExist:
        return Response({'error': 'DataSource not found'}, status=404)

    uploaded_file = request.FILES.get('file')
    if not uploaded_file:
        return Response({'error': 'No file provided'}, status=400)

    content = uploaded_file.read()
    file_hash = hashlib.sha256(content).hexdigest()

    # Warn on re-upload of identical file
    existing = ImportBatch.objects.filter(org=org, source=source, file_hash=file_hash).first()
    if existing:
        return Response({
            'warning': f'This exact file was already uploaded on {existing.started_at.date()} '
                       f'(batch {existing.id}). Proceeding anyway.',
            'duplicate_of': str(existing.id),
        }, status=200)

    with transaction.atomic():
        batch = ImportBatch.objects.create(
            source=source,
            org=org,
            status=ImportBatch.STATUS_PROCESSING,
            file_name=uploaded_file.name,
            file_hash=file_hash,
            uploaded_by=request.user,
        )

        parser_fn = {
            DataSource.SOURCE_SAP: sap_parser.parse,
            DataSource.SOURCE_UTILITY: utility_parser.parse,
            DataSource.SOURCE_TRAVEL: travel_parser.parse,
        }[source.source_type]

        normalize_fn = {
            DataSource.SOURCE_SAP: normalize_sap_row,
            DataSource.SOURCE_UTILITY: normalize_utility_row,
            DataSource.SOURCE_TRAVEL: normalize_travel_row,
        }[source.source_type]

        total = success = errors = warnings = 0
        error_details = []
        records_to_create = []

        for result in parser_fn(content):
            total += 1
            raw = RawRecord(
                batch=batch,
                org=org,
                source_row_number=result['row_number'],
                raw_data=result['raw_data'],
                parse_status=RawRecord.PARSE_OK if not result['error'] else RawRecord.PARSE_ERROR,
                parse_error=result['error'] or '',
            )
            raw.save()

            if result['error']:
                errors += 1
                error_details.append({'row': result['row_number'], 'error': result['error']})
                continue

            try:
                normalized = normalize_fn(result['parsed'], raw, org)
                normalized.save()
                if normalized.flags:
                    warnings += 1
                else:
                    success += 1
            except Exception as e:
                errors += 1
                raw.parse_status = RawRecord.PARSE_ERROR
                raw.parse_error = f"Normalization error: {str(e)}"
                raw.save()
                error_details.append({'row': result['row_number'], 'error': str(e)})

        batch.status = ImportBatch.STATUS_COMPLETED
        batch.completed_at = timezone.now()
        batch.total_rows = total
        batch.success_rows = success
        batch.error_rows = errors
        batch.warning_rows = warnings
        batch.error_details = error_details[:100]  # cap stored errors
        batch.save()

        AuditEvent.objects.create(
            org=org,
            batch=batch,
            user=request.user,
            event_type=AuditEvent.EVENT_BATCH_UPLOADED,
            after_state={
                'file_name': batch.file_name,
                'total_rows': total,
                'success_rows': success,
                'error_rows': errors,
            },
            ip_address=request.META.get('REMOTE_ADDR'),
        )

    return Response(ImportBatchSerializer(batch).data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def batch_detail(request, batch_id):
    org = get_user_org(request)
    try:
        batch = ImportBatch.objects.get(id=batch_id, org=org)
    except ImportBatch.DoesNotExist:
        return Response({'error': 'Not found'}, status=404)
    return Response(ImportBatchSerializer(batch).data)
