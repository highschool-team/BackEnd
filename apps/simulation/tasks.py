import json
import random
import redis
from decimal import Decimal
from datetime import datetime, timezone

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.db.models import F

from apps.authentication.models import User
from apps.teams.models import Team, TeamProvider
from apps.usage.models import UsageLog
from apps.alerts.models import Alert
from common.constants import (
    PROVIDER_CONFIG,
    TOKEN_COST_CONFIG,
    REDIS_ALERTS_CHANNEL,
)


def _get_redis():
    return redis.from_url(settings.REDIS_URL)


def _activity_profile(hour_kst: int) -> tuple[int, int]:
    """시간대별 (활성 유저 수 범위) 반환"""
    if 9 <= hour_kst < 12:    # 오전 피크
        return (8, 14)
    elif 12 <= hour_kst < 13:  # 점심
        return (2, 5)
    elif 13 <= hour_kst < 18:  # 오후
        return (6, 12)
    elif 18 <= hour_kst < 20:  # 퇴근 직후
        return (1, 4)
    elif 20 <= hour_kst < 23:  # 야근
        return (0, 3)
    else:                       # 새벽
        return (0, 1)


def _token_range(hour_kst: int) -> tuple[int, int, int, int]:
    """시간대별 (input_min, input_max, output_min, output_max) 반환"""
    if 9 <= hour_kst < 18:
        return (100, 2000, 80, 900)
    elif 18 <= hour_kst < 23:
        return (50, 1200, 50, 600)
    else:
        return (30, 500, 30, 200)


def _publish_alert(r, alert: Alert):
    payload = {
        'id': str(alert.id),
        'type': alert.type,
        'severity': alert.severity,
        'team': alert.team.name,
        'provider': alert.provider_name,
        'message': alert.message,
        'created_at': alert.created_at.isoformat(),
        'read': alert.read,
    }
    r.publish(REDIS_ALERTS_CHANNEL, json.dumps(payload))


def _check_thresholds(team: Team, provider: TeamProvider, r):
    provider.refresh_from_db()
    team.refresh_from_db()

    if provider.limit <= 0:
        return

    ratio = float(provider.spent) / float(provider.limit)

    if ratio >= 1.0:
        if team.status != 'BLOCKED':
            Team.objects.filter(pk=team.pk).update(status='BLOCKED')
        if not Alert.objects.filter(team=team, provider_name=provider.name, type='blocked').exists():
            alert = Alert.objects.create(
                type='blocked',
                severity='high',
                team=team,
                provider_name=provider.name,
                message=f"{team.name}의 {provider.name} 한도(${provider.limit})를 초과하여 차단됐습니다. (사용: ${provider.spent:.2f})",
            )
            _publish_alert(r, alert)

    elif ratio >= 0.8:
        if not Alert.objects.filter(team=team, provider_name=provider.name, type='quota_warning').exists():
            alert = Alert.objects.create(
                type='quota_warning',
                severity='high' if ratio >= 0.9 else 'medium',
                team=team,
                provider_name=provider.name,
                message=f"{team.name}의 {provider.name} 한도 {ratio:.0%} 도달 (${provider.spent:.2f} / ${provider.limit})",
            )
            _publish_alert(r, alert)


@shared_task(name='apps.simulation.tasks.simulate_company_usage')
def simulate_company_usage():
    now = datetime.now(timezone.utc)
    hour_kst = (now.hour + 9) % 24

    min_users, max_users = _activity_profile(hour_kst)
    num_active = random.randint(min_users, max_users)

    if num_active == 0:
        return f"[{hour_kst}시 KST] 활동 없음"

    in_min, in_max, out_min, out_max = _token_range(hour_kst)

    users = list(
        User.objects.filter(team__isnull=False, role__in=['MEMBER', 'PARTLEAD'])
        .select_related('team')
    )
    if not users:
        return "유저 없음"

    selected = random.sample(users, min(num_active, len(users)))
    r = _get_redis()
    logs_created = 0

    for user in selected:
        team = user.team
        providers = list(TeamProvider.objects.filter(team=team, spent__lt=F('limit')))
        if not providers:
            continue

        provider = random.choice(providers)
        config = PROVIDER_CONFIG.get(provider.name, {})
        allowed_models = config.get('allowed_models', [])
        if not allowed_models:
            continue

        model = provider.selected_model or random.choice(allowed_models)
        cost_config = TOKEN_COST_CONFIG.get(model)
        if not cost_config:
            continue

        # 유저 역할별 사용량 차이 (partlead는 더 많이 씀)
        multiplier = 1.3 if user.role == 'PARTLEAD' else 1.0
        input_tokens = max(10, int(random.randint(in_min, in_max) * multiplier))
        output_tokens = max(10, int(random.randint(out_min, out_max) * multiplier))

        cost = (
            Decimal(str(cost_config['input'])) * Decimal(str(input_tokens)) / Decimal('1000') +
            Decimal(str(cost_config['output'])) * Decimal(str(output_tokens)) / Decimal('1000')
        )

        # 한도 초과 방지
        provider.refresh_from_db()
        remaining = provider.limit - provider.spent
        if remaining <= 0:
            continue
        if cost > remaining:
            cost = remaining

        with transaction.atomic():
            TeamProvider.objects.filter(pk=provider.pk).update(spent=F('spent') + cost)
            UsageLog.objects.create(
                user=user,
                team=team,
                provider_name=provider.name,
                model_name=model,
                cost=cost,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

        _check_thresholds(team, provider, r)
        logs_created += 1

    return f"[{hour_kst}시 KST] {logs_created}건 사용량 기록"
