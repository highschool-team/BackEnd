from decimal import Decimal
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from common.permissions import IsTechLead, IsPartLeadOrAbove
from common.constants import PROVIDER_CONFIG, REDIS_IP_ALLOWLIST_KEY, REDIS_SUSPENDED_KEY, REDIS_PROVIDER_KEY
from common.redis_client import get_redis
from .models import Team, TeamProvider, TeamIPAllowlist
from .serializers import (
    TeamSerializer,
    TeamProviderSerializer,
    TeamBudgetSerializer,
    AddProviderSerializer,
    ProviderLimitSerializer,
    ProviderModelSerializer,
    TeamIPAllowlistSerializer,
    ProviderRateLimitSerializer,
)


class TeamListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='팀 목록 조회',
        responses={200: TeamSerializer(many=True)},
        tags=['Teams'],
    )
    def get(self, request):
        user = request.user
        if user.role == 'TECHLEAD':
            teams = Team.objects.prefetch_related('providers').all()
        elif user.role in ('PARTLEAD', 'MEMBER'):
            if user.team:
                teams = Team.objects.prefetch_related('providers').filter(id=user.team_id)
            else:
                teams = Team.objects.none()
        else:
            return Response(
                {'error': 'forbidden', 'message': 'You do not have permission to view teams.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response(TeamSerializer(teams, many=True).data)


class TeamDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='팀 단건 조회',
        responses={200: TeamSerializer},
        tags=['Teams'],
    )
    def get(self, request, pk):
        team = get_object_or_404(Team, pk=pk)
        user = request.user

        if user.role == 'TECHLEAD':
            pass
        elif user.role in ('PARTLEAD', 'MEMBER'):
            if str(user.team_id) != str(pk):
                return Response(
                    {'error': 'forbidden', 'message': 'You can only view your own team.'},
                    status=status.HTTP_403_FORBIDDEN,
                )
        else:
            return Response(
                {'error': 'forbidden', 'message': 'You do not have permission to view teams.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        return Response(TeamSerializer(team).data)


class TeamBudgetView(APIView):
    permission_classes = [IsTechLead]

    @extend_schema(
        summary='팀 예산 수정 (techlead 전용)',
        request=TeamBudgetSerializer,
        responses={200: TeamSerializer},
        tags=['Teams'],
    )
    def put(self, request, pk):
        team = get_object_or_404(Team, pk=pk)
        serializer = TeamBudgetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        team.budget = serializer.validated_data['budget']
        team.save(update_fields=['budget', 'updated_at'])

        return Response(TeamSerializer(team).data)


class TeamProviderListView(APIView):
    permission_classes = [IsTechLead]

    @extend_schema(
        summary='팀에 AI 프로바이더 추가 (techlead 전용)',
        request=AddProviderSerializer,
        responses={201: TeamProviderSerializer},
        tags=['Teams'],
    )
    def post(self, request, pk):
        team = get_object_or_404(Team, pk=pk)
        serializer = AddProviderSerializer(data=request.data, context={'team': team})
        serializer.is_valid(raise_exception=True)

        provider = TeamProvider.objects.create(
            team=team,
            name=serializer.validated_data['name'],
            limit=Decimal('10.0000'),
            spent=Decimal('0.0000'),
        )

        return Response(TeamProviderSerializer(provider).data, status=status.HTTP_201_CREATED)


class TeamProviderDetailView(APIView):
    permission_classes = [IsTechLead]

    @extend_schema(
        summary='팀에서 프로바이더 제거 (techlead 전용)',
        responses={204: None},
        tags=['Teams'],
    )
    def delete(self, request, pk, provider_name):
        team = get_object_or_404(Team, pk=pk)
        provider = get_object_or_404(TeamProvider, team=team, name=provider_name)
        provider.delete()
        get_redis().delete(REDIS_IP_ALLOWLIST_KEY.format(team_id=str(pk)))
        from apps.proxy.pipeline import invalidate_provider_cache
        invalidate_provider_cache(pk, provider_name, get_redis())
        return Response(status=status.HTTP_204_NO_CONTENT)


class TeamProviderLimitView(APIView):
    permission_classes = [IsPartLeadOrAbove]

    @extend_schema(
        summary='프로바이더 예산 한도 수정 (techlead, partlead)',
        request=ProviderLimitSerializer,
        responses={200: TeamProviderSerializer},
        tags=['Teams'],
    )
    def put(self, request, pk, provider_name):
        team = get_object_or_404(Team, pk=pk)
        user = request.user

        if user.role == 'PARTLEAD' and str(user.team_id) != str(pk):
            return Response(
                {'error': 'forbidden', 'message': 'You can only update limits for your own team.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        provider = get_object_or_404(TeamProvider, team=team, name=provider_name)
        serializer = ProviderLimitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        new_limit = serializer.validated_data['limit']
        other_total = (
            team.providers.exclude(name=provider_name)
            .aggregate(total=Sum('limit'))['total'] or Decimal('0.0000')
        )

        if other_total + new_limit > team.budget:
            return Response(
                {
                    'error': 'limit_exceeded',
                    'message': f"프로바이더 한도 합계({other_total + new_limit})가 팀 예산({team.budget})을 초과합니다.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        provider.limit = new_limit
        provider.save(update_fields=['limit', 'updated_at'])

        from apps.proxy.pipeline import invalidate_provider_cache
        invalidate_provider_cache(pk, provider_name, get_redis())

        return Response(TeamProviderSerializer(provider).data)


class TeamProviderModelView(APIView):
    permission_classes = [IsPartLeadOrAbove]

    @extend_schema(
        summary='사용 모델 선택 (techlead, partlead)',
        request=ProviderModelSerializer,
        responses={200: TeamProviderSerializer},
        tags=['Teams'],
    )
    def put(self, request, pk, provider_name):
        team = get_object_or_404(Team, pk=pk)
        user = request.user

        if user.role == 'PARTLEAD' and str(user.team_id) != str(pk):
            return Response(
                {'error': 'forbidden', 'message': 'You can only update models for your own team.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        provider = get_object_or_404(TeamProvider, team=team, name=provider_name)
        serializer = ProviderModelSerializer(data=request.data, context={'provider_name': provider_name})
        serializer.is_valid(raise_exception=True)

        provider.selected_model = serializer.validated_data['model']
        provider.save(update_fields=['selected_model', 'updated_at'])

        from apps.proxy.pipeline import invalidate_provider_cache
        invalidate_provider_cache(pk, provider_name, get_redis())

        return Response(TeamProviderSerializer(provider).data)


class TeamIPAllowlistView(APIView):
    permission_classes = [IsTechLead]

    @extend_schema(
        summary='IP 허용 목록 조회 (techlead 전용)',
        responses={200: TeamIPAllowlistSerializer(many=True)},
        tags=['Teams'],
    )
    def get(self, request, pk):
        team = get_object_or_404(Team, pk=pk)
        entries = TeamIPAllowlist.objects.filter(team=team).order_by('created_at')
        return Response(TeamIPAllowlistSerializer(entries, many=True).data)

    @extend_schema(
        summary='IP 허용 목록에 추가 (techlead 전용)',
        request=TeamIPAllowlistSerializer,
        responses={201: TeamIPAllowlistSerializer},
        tags=['Teams'],
    )
    def post(self, request, pk):
        team = get_object_or_404(Team, pk=pk)
        serializer = TeamIPAllowlistSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        entry, created = TeamIPAllowlist.objects.get_or_create(
            team=team,
            ip_cidr=serializer.validated_data['ip_cidr'],
            defaults={'description': serializer.validated_data.get('description', '')},
        )
        if not created:
            return Response(
                {'error': 'duplicate', 'message': f"IP '{entry.ip_cidr}' is already in the allowlist."},
                status=status.HTTP_409_CONFLICT,
            )

        # Invalidate Redis cache so next request re-loads from DB
        get_redis().delete(REDIS_IP_ALLOWLIST_KEY.format(team_id=str(team.id)))

        return Response(TeamIPAllowlistSerializer(entry).data, status=status.HTTP_201_CREATED)


class TeamIPAllowlistDetailView(APIView):
    permission_classes = [IsTechLead]

    @extend_schema(
        summary='IP 허용 목록에서 삭제 (techlead 전용)',
        responses={204: None},
        tags=['Teams'],
    )
    def delete(self, request, pk, entry_id):
        team = get_object_or_404(Team, pk=pk)
        entry = get_object_or_404(TeamIPAllowlist, pk=entry_id, team=team)
        entry.delete()
        get_redis().delete(REDIS_IP_ALLOWLIST_KEY.format(team_id=str(team.id)))
        return Response(status=status.HTTP_204_NO_CONTENT)


class TeamProviderRateLimitView(APIView):
    permission_classes = [IsTechLead]

    @extend_schema(
        summary='프로바이더 분당 호출 제한 수정 (techlead 전용)',
        request=ProviderRateLimitSerializer,
        responses={200: TeamProviderSerializer},
        tags=['Teams'],
    )
    def put(self, request, pk, provider_name):
        team = get_object_or_404(Team, pk=pk)
        provider = get_object_or_404(TeamProvider, team=team, name=provider_name)
        serializer = ProviderRateLimitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        provider.rate_limit = serializer.validated_data['rate_limit']
        provider.save(update_fields=['rate_limit', 'updated_at'])

        from apps.proxy.pipeline import invalidate_provider_cache
        invalidate_provider_cache(pk, provider_name, get_redis())

        return Response(TeamProviderSerializer(provider).data)


class TeamProviderUnsuspendView(APIView):
    permission_classes = [IsTechLead]

    @extend_schema(
        summary='정지된 프로바이더 접근 복구 (techlead 전용)',
        request=None,
        responses={200: TeamProviderSerializer},
        tags=['Teams'],
    )
    def post(self, request, pk, provider_name):
        team = get_object_or_404(Team, pk=pk)
        provider = get_object_or_404(TeamProvider, team=team, name=provider_name)

        provider.is_suspended = False
        provider.save(update_fields=['is_suspended', 'updated_at'])

        r = get_redis()
        pipe = r.pipeline()
        pipe.delete(REDIS_SUSPENDED_KEY.format(team_id=str(team.id), provider=provider_name))
        pipe.delete(REDIS_PROVIDER_KEY.format(team_id=str(team.id), provider=provider_name))
        pipe.execute()

        return Response(TeamProviderSerializer(provider).data)
