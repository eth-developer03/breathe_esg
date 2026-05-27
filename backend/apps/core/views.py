from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.core.management import call_command
from decouple import config
from .serializers import UserSerializer, OrganizationSerializer


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me(request):
    return Response(UserSerializer(request.user).data)


@api_view(['GET'])
@permission_classes([AllowAny])
def setup(request):
    """
    One-time setup endpoint — runs migrate + seed_demo.
    Protected by SETUP_SECRET env var. Hit this once after deploy if
    the build command didn't run the seed automatically.
    Usage: /api/setup/?secret=YOUR_SETUP_SECRET
    """
    secret = config('SETUP_SECRET', default='')
    if not secret or request.query_params.get('secret') != secret:
        return Response({'error': 'Forbidden — set SETUP_SECRET env var and pass ?secret='}, status=403)

    try:
        call_command('migrate', '--no-input')
        call_command('seed_demo')
        return Response({'status': 'ok', 'message': 'Migrations run and demo data seeded.'})
    except Exception as e:
        return Response({'status': 'error', 'message': str(e)}, status=500)
