import json
import redis
from django.conf import settings
from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response

from common.permissions import IsDevOpsOrTechLead
from common.constants import (
    PROVISIONING_STEPS,
    REDIS_PROVISIONING_CHANNEL_PREFIX,
    REDIS_TASK_KEY_PREFIX,
)
from .models import ProvisioningTask
from .serializers import (
    OnboardSerializer,
    OffboardSerializer,
    ProvisioningTaskSerializer,
    ProvisioningResponseSerializer,
)
from .tasks import run_onboard_task, run_offboard_task


def get_redis_client():
    return redis.from_url(settings.REDIS_URL)


class OnboardView(APIView):
    permission_classes = [IsDevOpsOrTechLead]

    @extend_schema(
        summary='입사 프로세스 실행',
        request=OnboardSerializer,
        responses={202: ProvisioningResponseSerializer},
        tags=['Provisioning'],
    )
    def post(self, request):
        serializer = OnboardSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email']
        team_id = serializer.validated_data.get('team_id')
        role = serializer.validated_data.get('role', 'MEMBER')

        steps = [{'service': s, 'status': 'pending'} for s in PROVISIONING_STEPS]
        task = ProvisioningTask.objects.create(
            email=email,
            task_type='onboard',
            status='processing',
            steps=steps,
        )

        run_onboard_task.delay(str(task.task_id), email, str(team_id) if team_id else None, role)

        return Response({
            'task_id': str(task.task_id),
            'email': email,
            'status': 'processing',
        }, status=status.HTTP_202_ACCEPTED)


class OffboardView(APIView):
    permission_classes = [IsDevOpsOrTechLead]

    @extend_schema(
        summary='퇴사 프로세스 실행',
        request=OffboardSerializer,
        responses={202: ProvisioningResponseSerializer},
        tags=['Provisioning'],
    )
    def post(self, request):
        serializer = OffboardSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email']
        figma_transfer_to = serializer.validated_data.get('figma_transfer_to')

        steps = [{'service': s, 'status': 'pending'} for s in PROVISIONING_STEPS]
        task = ProvisioningTask.objects.create(
            email=email,
            figma_transfer_to=figma_transfer_to,
            task_type='offboard',
            status='processing',
            steps=steps,
        )

        run_offboard_task.delay(str(task.task_id), email, figma_transfer_to)

        return Response({
            'task_id': str(task.task_id),
            'email': email,
            'status': 'processing',
        }, status=status.HTTP_202_ACCEPTED)


class ProvisioningTaskDetailView(APIView):
    permission_classes = [IsDevOpsOrTechLead]

    @extend_schema(
        summary='프로비저닝 진행 상태 조회',
        responses={200: ProvisioningTaskSerializer},
        tags=['Provisioning'],
    )
    def get(self, request, task_id):
        r = get_redis_client()
        cached = r.get(f"{REDIS_TASK_KEY_PREFIX}{task_id}")

        if cached:
            try:
                return Response(json.loads(cached))
            except (json.JSONDecodeError, TypeError):
                pass

        task = get_object_or_404(ProvisioningTask, task_id=task_id)
        return Response(ProvisioningTaskSerializer(task).data)


class ProvisioningTaskStreamView(APIView):
    permission_classes = [IsDevOpsOrTechLead]

    @extend_schema(
        summary='SSE 프로비저닝 단계별 진행 스트림',
        responses={(200, 'text/event-stream'): str},
        tags=['Provisioning'],
    )
    def get(self, request, task_id):
        r = get_redis_client()
        channel = f"{REDIS_PROVISIONING_CHANNEL_PREFIX}{task_id}"

        def event_stream():
            pubsub = r.pubsub()
            pubsub.subscribe(channel)

            cached = r.get(f"{REDIS_TASK_KEY_PREFIX}{task_id}")
            if cached:
                try:
                    yield f"data: {json.dumps(json.loads(cached))}\n\n"
                except (json.JSONDecodeError, TypeError):
                    pass

            try:
                yield ": connected\n\n"
                while True:
                    msg = pubsub.get_message(timeout=30)
                    if msg and msg['type'] == 'message':
                        data = msg['data']
                        if isinstance(data, bytes):
                            data = data.decode('utf-8')
                        yield f"data: {data}\n\n"

                        try:
                            if json.loads(data).get('overall_status') in ('done', 'failed'):
                                break
                        except (json.JSONDecodeError, TypeError):
                            pass
            except GeneratorExit:
                pubsub.unsubscribe()
                pubsub.close()

        response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        return response
