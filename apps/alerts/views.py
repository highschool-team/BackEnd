import json
from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from common.constants import REDIS_ALERTS_CHANNEL
from common.redis_client import get_redis
from .models import Alert
from .serializers import AlertSerializer


class AlertListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='보안 알림 목록',
        parameters=[
            OpenApiParameter('status', OpenApiTypes.STR, enum=['unread', 'read', 'all'], default='all'),
            OpenApiParameter('severity', OpenApiTypes.STR, enum=['high', 'medium', 'low'], required=False),
            OpenApiParameter('limit', OpenApiTypes.INT, default=50),
        ],
        responses={200: AlertSerializer(many=True)},
        tags=['Alerts'],
    )
    def get(self, request):
        alerts = Alert.objects.select_related('team').all()

        alert_status = request.query_params.get('status', 'all')
        if alert_status == 'unread':
            alerts = alerts.filter(read=False)
        elif alert_status == 'read':
            alerts = alerts.filter(read=True)

        severity = request.query_params.get('severity')
        if severity:
            alerts = alerts.filter(severity=severity)

        try:
            limit = int(request.query_params.get('limit', 50))
        except ValueError:
            limit = 50
        alerts = alerts[:limit]

        return Response(AlertSerializer(alerts, many=True).data)


class AlertReadView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='알림 읽음 처리',
        request=None,
        responses={200: AlertSerializer},
        tags=['Alerts'],
    )
    def patch(self, request, pk):
        alert = get_object_or_404(Alert, pk=pk)
        alert.read = True
        alert.save(update_fields=['read'])
        return Response(AlertSerializer(alert).data)


class AlertStreamView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='SSE 실시간 알림 스트림',
        responses={(200, 'text/event-stream'): OpenApiTypes.STR},
        tags=['Alerts'],
    )
    def get(self, request):
        r = get_redis()

        def event_stream():
            pubsub = r.pubsub()
            pubsub.subscribe(REDIS_ALERTS_CHANNEL)
            try:
                yield ": connected\n\n"
                while True:
                    msg = pubsub.get_message(timeout=30)
                    if msg and msg['type'] == 'message':
                        data = msg['data']
                        if isinstance(data, bytes):
                            data = data.decode('utf-8')
                        yield f"data: {data}\n\n"
            except GeneratorExit:
                pubsub.unsubscribe()
                pubsub.close()

        response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        return response
