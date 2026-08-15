import json
import os
import random
from decimal import Decimal

import httpx
from django.conf import settings
from django.db import transaction
from django.db.models import F
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from common.constants import PROVIDER_CONFIG, TOKEN_COST_CONFIG
from common.redis_client import get_redis
from apps.teams.models import TeamProvider
from apps.usage.models import UsageLog
from apps.alerts.models import Alert

from .pipeline import (
    get_provider_meta,
    run_pipeline,
    update_budget_cache,
    publish_alert,
)

_PIPELINE_STATUS = {
    'ip_blocked': status.HTTP_403_FORBIDDEN,
    'provider_suspended': status.HTTP_403_FORBIDDEN,
    'injection_blocked': status.HTTP_403_FORBIDDEN,
    'quota_exceeded': status.HTTP_429_TOO_MANY_REQUESTS,
    'rate_limited': status.HTTP_429_TOO_MANY_REQUESTS,
}


def calculate_cost(model_name: str, input_tokens: int, output_tokens: int) -> Decimal:
    cost_config = TOKEN_COST_CONFIG.get(model_name)
    if not cost_config:
        return Decimal('0')
    input_cost = Decimal(str(cost_config['input'])) * Decimal(str(input_tokens)) / Decimal('1000')
    output_cost = Decimal(str(cost_config['output'])) * Decimal(str(output_tokens)) / Decimal('1000')
    return input_cost + output_cost


def _build_mock_response(provider_name: str, model: str, input_tokens: int, output_tokens: int) -> dict:
    if provider_name == 'OpenAI':
        return {
            "id": f"chatcmpl-mock{random.randint(10000,99999)}",
            "object": "chat.completion",
            "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "[Mock response]"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": input_tokens, "completion_tokens": output_tokens, "total_tokens": input_tokens + output_tokens},
        }
    if provider_name == 'Anthropic':
        return {
            "id": f"msg_mock{random.randint(10000,99999)}",
            "type": "message", "role": "assistant", "model": model,
            "content": [{"type": "text", "text": "[Mock response]"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
        }
    return {
        "candidates": [{"content": {"parts": [{"text": "[Mock response]"}], "role": "model"}, "finishReason": "STOP", "index": 0}],
        "usageMetadata": {"promptTokenCount": input_tokens, "candidatesTokenCount": output_tokens, "totalTokenCount": input_tokens + output_tokens},
        "modelVersion": model,
    }


def _record_spend(provider_pk, user, team_id, provider_name, model_name, cost, input_tokens, output_tokens, r):
    """Write spend to DB atomically, then sync fresh value to Redis budget cache."""
    with transaction.atomic():
        TeamProvider.objects.filter(pk=provider_pk).update(spent=F('spent') + cost)
        UsageLog.objects.create(
            user=user,
            team_id=team_id,
            provider_name=provider_name,
            model_name=model_name,
            cost=cost,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    # Re-read fresh spent from DB so Redis budget stays accurate
    row = TeamProvider.objects.filter(pk=provider_pk).values('spent', 'limit').first()
    if row:
        update_budget_cache(team_id, provider_name, float(row['spent']), float(row['limit']), r)


def _check_thresholds(provider_pk, team_id, provider_name, r):
    """After spend, check alert thresholds. Runs post-LLM — DB latency is fine here."""
    from apps.teams.models import Team
    provider = TeamProvider.objects.select_related('team').get(pk=provider_pk)
    team = provider.team

    if provider.limit <= 0:
        return

    ratio = float(provider.spent) / float(provider.limit)

    if ratio >= 1.0:
        if team.status != 'BLOCKED':
            from apps.teams.models import Team as T
            T.objects.filter(pk=team.pk).update(status='BLOCKED')
        if not Alert.objects.filter(team=team, provider_name=provider_name, type='blocked').exists():
            alert = Alert.objects.create(
                type='blocked', severity='high', team=team, provider_name=provider_name,
                message=(
                    f"Team '{team.name}' BLOCKED on {provider_name}. "
                    f"Limit ${provider.limit} reached (spent ${provider.spent})."
                ),
            )
            publish_alert(r, alert)

    elif ratio >= 0.80:
        if not Alert.objects.filter(team=team, provider_name=provider_name, type='quota_warning').exists():
            alert = Alert.objects.create(
                type='quota_warning', severity='medium', team=team, provider_name=provider_name,
                message=(
                    f"Team '{team.name}' used {ratio:.0%} of {provider_name} quota "
                    f"(${provider.spent} / ${provider.limit})."
                ),
            )
            publish_alert(r, alert)


class BaseProxyView(APIView):
    permission_classes = [IsAuthenticated]
    provider_name = None

    def post(self, request, path=''):
        user = request.user
        team_id = user.team_id  # FK column — no extra DB query
        if not team_id:
            return Response(
                {'error': 'no_team', 'message': 'User is not assigned to a team.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        r = get_redis()

        # ── Fetch provider metadata (Redis cache hit = 0 DB queries) ──────────
        provider_meta = get_provider_meta(team_id, self.provider_name, r)
        if provider_meta is None:
            return Response(
                {
                    'error': 'provider_not_configured',
                    'message': f"Provider '{self.provider_name}' is not configured for your team.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if provider_meta['team_status'] == 'BLOCKED':
            return Response(
                {'error': 'quota_exceeded', 'message': 'Your team has been blocked due to quota exceeded.'},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        # Parse body before pipeline (Stage 3 needs it)
        try:
            body = json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            body = {}

        # ── 3 stages, 1 Redis round trip ──────────────────────────────────────
        result = run_pipeline(request, team_id, provider_meta, body, user, r)
        if not result.allowed:
            return Response(
                {'error': result.error_code, 'message': result.message},
                status=_PIPELINE_STATUS.get(result.error_code, status.HTTP_403_FORBIDDEN),
            )

        # ── Stage 4: forward with real API key ────────────────────────────────
        config = PROVIDER_CONFIG[self.provider_name]
        allowed_models = config.get('allowed_models', [])
        model_name = body.get('model', provider_meta['selected_model'])

        if model_name and model_name not in allowed_models:
            return Response(
                {'error': 'model_not_allowed', 'message': f"Model '{model_name}' is not allowed. Allowed: {allowed_models}"},
                status=status.HTTP_403_FORBIDDEN,
            )

        effective_model = model_name or provider_meta['selected_model'] or ''

        if getattr(settings, 'AI_MOCK_MODE', False):
            input_tokens = random.randint(50, 2000)
            output_tokens = random.randint(50, 800)
            cost = calculate_cost(effective_model, input_tokens, output_tokens)
            _record_spend(provider_meta['pk'], user, team_id, self.provider_name, effective_model, cost, input_tokens, output_tokens, r)
            _check_thresholds(provider_meta['pk'], team_id, self.provider_name, r)
            return Response(_build_mock_response(self.provider_name, effective_model, input_tokens, output_tokens))

        api_key = os.environ.get(config['api_key_env'], '')
        header_prefix = config['header_prefix']
        upstream_headers = {
            config['header_key']: f"{header_prefix} {api_key}" if header_prefix else api_key,
            'Content-Type': 'application/json',
        }
        for hdr in ('Accept', 'anthropic-version', 'anthropic-beta'):
            val = request.META.get(f'HTTP_{hdr.upper().replace("-", "_")}')
            if val:
                upstream_headers[hdr] = val

        upstream_url = f"{config['api_base']}/{path}" if path else config['api_base']

        try:
            with httpx.Client(timeout=120.0) as client:
                upstream_response = client.post(upstream_url, content=request.body, headers=upstream_headers)
        except httpx.RequestError as e:
            return Response(
                {'error': 'upstream_error', 'message': f"Failed to reach {self.provider_name}: {str(e)}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        input_tokens = output_tokens = 0

        if upstream_response.status_code == 200:
            try:
                resp_json = upstream_response.json()
                usage = resp_json.get('usage', {})
                if self.provider_name == 'OpenAI':
                    input_tokens = usage.get('prompt_tokens', 0) or usage.get('input_tokens', 0)
                    output_tokens = usage.get('completion_tokens', 0)
                    if 'model' in resp_json:
                        resp_model = resp_json['model']
                        for m in allowed_models:
                            if m.lower().replace(' ', '-') in resp_model.lower() or resp_model.lower() in m.lower():
                                effective_model = m
                                break
                elif self.provider_name == 'Anthropic':
                    input_tokens = usage.get('input_tokens', 0)
                    output_tokens = usage.get('output_tokens', 0)
                elif self.provider_name == 'Gemini':
                    usage = resp_json.get('usageMetadata', {})
                    input_tokens = usage.get('promptTokenCount', 0)
                    output_tokens = usage.get('candidatesTokenCount', 0)
            except (json.JSONDecodeError, AttributeError):
                pass

            cost = calculate_cost(effective_model, input_tokens, output_tokens)
            _record_spend(provider_meta['pk'], user, team_id, self.provider_name, effective_model, cost, input_tokens, output_tokens, r)
            _check_thresholds(provider_meta['pk'], team_id, self.provider_name, r)

        try:
            return Response(upstream_response.json(), status=upstream_response.status_code)
        except json.JSONDecodeError:
            return Response(upstream_response.text, status=upstream_response.status_code, content_type='application/json')


class OpenAIProxyView(BaseProxyView):
    provider_name = 'OpenAI'

    @extend_schema(summary='OpenAI API 프록시', tags=['Proxy'])
    def post(self, request, path=''):
        return super().post(request, path)


class AnthropicProxyView(BaseProxyView):
    provider_name = 'Anthropic'

    @extend_schema(summary='Anthropic API 프록시', tags=['Proxy'])
    def post(self, request, path=''):
        return super().post(request, path)


class GeminiProxyView(BaseProxyView):
    provider_name = 'Gemini'

    @extend_schema(summary='Gemini API 프록시', tags=['Proxy'])
    def post(self, request, path=''):
        return super().post(request, path)
