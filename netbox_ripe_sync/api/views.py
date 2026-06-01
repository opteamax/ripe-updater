import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ReadOnlyModelViewSet

from ..models import (
    RipeSyncLog,
    RipeRouteObject,
    RipeDomainObject,
    RipeInetnumObject,
    RipeChange,
)
from .serializers import (
    RipeSyncLogSerializer,
    RipeRouteObjectSerializer,
    RipeDomainObjectSerializer,
    RipeInetnumObjectSerializer,
    RipeChangeSerializer,
    TriggerSyncSerializer,
)

logger = logging.getLogger('netbox.plugins.ripe_sync')


class RipeSyncLogViewSet(ReadOnlyModelViewSet):
    """Read-only list/detail for RIPE sync log entries."""

    queryset = RipeSyncLog.objects.order_by('-created')
    serializer_class = RipeSyncLogSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        prefix = self.request.query_params.get('prefix')
        if prefix:
            qs = qs.filter(prefix=prefix)
        return qs


class RipeRouteObjectViewSet(ReadOnlyModelViewSet):
    """Read-only list/detail for imported RIPE route objects."""

    queryset = RipeRouteObject.objects.all()
    serializer_class = RipeRouteObjectSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        prefix = self.request.query_params.get('prefix')
        if prefix:
            qs = qs.filter(prefix=prefix)
        origin = self.request.query_params.get('origin')
        if origin:
            qs = qs.filter(origin=origin)
        return qs


class RipeDomainObjectViewSet(ReadOnlyModelViewSet):
    queryset = RipeDomainObject.objects.all()
    serializer_class = RipeDomainObjectSerializer


class RipeInetnumObjectViewSet(ReadOnlyModelViewSet):
    queryset = RipeInetnumObject.objects.all()
    serializer_class = RipeInetnumObjectSerializer


class RipeChangeViewSet(ReadOnlyModelViewSet):
    queryset = RipeChange.objects.all()
    serializer_class = RipeChangeSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)
        return qs


class TriggerSyncView(APIView):
    """POST {prefix_id: N} to manually queue a RIPE sync for a NetBox prefix."""

    def post(self, request):
        serializer = TriggerSyncSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        from ipam.models import Prefix
        from ..models import RipeSyncLog
        from ..signals import _collect_and_enqueue

        prefix_id = serializer.validated_data['prefix_id']
        try:
            prefix = Prefix.objects.get(pk=prefix_id)
        except Prefix.DoesNotExist:
            return Response({'detail': f'Prefix {prefix_id} not found.'}, status=status.HTTP_404_NOT_FOUND)

        if not prefix.custom_field_data.get('ripe_report'):
            return Response(
                {'detail': 'ripe_report is not enabled for this prefix.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            _collect_and_enqueue(prefix, RipeSyncLog.ACTION_UPDATE)
        except Exception as exc:
            logger.exception(f'API manual sync failed for prefix {prefix_id}')
            return Response({'detail': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({'status': 'queued', 'prefix': str(prefix.prefix)})
