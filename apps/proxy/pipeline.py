"""
3-stage pre-request filtering pipeline.

All Redis reads happen in a SINGLE round trip on cache hit:
  GET  ip_allowlist   → Stage 1
  EXISTS suspended    → Stage 2
  HGET budget spent   → Stage 2
  HGET budget limit   → Stage 2
  INCR rate_counter   → Stage 2
  EXPIRE rate_counter → Stage 2

Stage 3 (injection) is pure Python — no Redis.
"""
import json
import ipaddress
import time
from typing import NamedTuple, Optional

from common.constants import (
    INJECTION_PATTERNS,
    REDIS_ALERTS_CHANNEL,
    REDIS_BUDGET_KEY,
    REDIS_IP_ALLOWLIST_KEY,
    REDIS_PROVIDER_KEY,
    REDIS_RATE_KEY,
    REDIS_SUSPENDED_KEY,
)


class PipelineResult(NamedTuple):
    allowed: bool
    error_code: Optional[str]
    message: Optional[str]


# ── Provider metadata cache (replaces TeamProvider DB query) ──────────────────

def get_provider_meta(team_id, provider_name: str, r) -> Optional[dict]:
    """
    Returns provider metadata from Redis (no DB on hit, ~0.1ms).
    Falls back to DB on miss, caches result for 60s.
    Returns None if provider not configured for this team.
    """
    key = REDIS_PROVIDER_KEY.format(team_id=str(team_id), provider=provider_name)
    cached = r.get(key)
    if cached:
        return json.loads(cached)

    from apps.teams.models import TeamProvider
    try:
        p = TeamProvider.objects.select_related('team').get(
            team_id=team_id, name=provider_name
        )
    except TeamProvider.DoesNotExist:
        return None

    data = {
        'pk': str(p.pk),
        'name': p.name,
        'limit': float(p.limit),
        'spent': float(p.spent),
        'rate_limit': p.rate_limit,
        'is_suspended': p.is_suspended,
        'selected_model': p.selected_model,
        'team_status': p.team.status,
    }
    r.setex(key, 60, json.dumps(data))
    return data


def invalidate_provider_cache(team_id, provider_name: str, r) -> None:
    r.delete(REDIS_PROVIDER_KEY.format(team_id=str(team_id), provider=provider_name))


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_client_ip(request) -> str:
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '0.0.0.0')


def publish_alert(r, alert) -> None:
    payload = {
        'id': str(alert.id),
        'type': alert.type,
        'severity': alert.severity,
        'team_id': str(alert.team_id),
        'team_name': alert.team.name,
        'provider_name': alert.provider_name,
        'message': alert.message,
        'created_at': alert.created_at.isoformat(),
    }
    r.publish(REDIS_ALERTS_CHANNEL, json.dumps(payload))

    # Slack 비동기 전송 (Celery)
    from apps.alerts.tasks import send_slack_alert
    send_slack_alert.delay(payload)


def _ip_in_cidrs(client_ip: str, cidrs: list) -> bool:
    try:
        addr = ipaddress.ip_address(client_ip)
        return any(addr in ipaddress.ip_network(c, strict=False) for c in cidrs)
    except ValueError:
        return False


def _load_ip_allowlist(team_id, r) -> list:
    from apps.teams.models import TeamIPAllowlist
    cidrs = list(
        TeamIPAllowlist.objects.filter(team_id=team_id).values_list('ip_cidr', flat=True)
    )
    r.setex(REDIS_IP_ALLOWLIST_KEY.format(team_id=str(team_id)), 300, json.dumps(cidrs))
    return cidrs


def _extract_prompt_text(body: dict, provider_name: str) -> str:
    texts = []
    if provider_name == 'Gemini':
        for content in body.get('contents', []):
            for part in content.get('parts', []):
                if isinstance(part.get('text'), str):
                    texts.append(part['text'])
        for part in body.get('systemInstruction', {}).get('parts', []):
            if isinstance(part.get('text'), str):
                texts.append(part['text'])
    else:
        for msg in body.get('messages', []):
            content = msg.get('content', '')
            if isinstance(content, str):
                texts.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get('type') == 'text':
                        texts.append(block.get('text', ''))
        system = body.get('system', '')
        if isinstance(system, str):
            texts.append(system)
        elif isinstance(system, list):
            for block in system:
                if isinstance(block, dict) and block.get('type') == 'text':
                    texts.append(block.get('text', ''))
    return '\n'.join(texts)


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run_pipeline(request, team_id, provider_meta: dict, body: dict, user, r) -> PipelineResult:
    """
    Executes all 3 filter stages in a SINGLE Redis round trip on cache hit.

    Pipeline sends 6 commands at once and waits for 1 response batch:
      [0] GET  ip_allowlist_key
      [1] EXISTS suspended_key
      [2] HGET budget_key 'spent'
      [3] HGET budget_key 'limit'
      [4] INCR rate_key
      [5] EXPIRE rate_key 120
    """
    team_id_str = str(team_id)
    provider_name = provider_meta['name']

    ip_key = REDIS_IP_ALLOWLIST_KEY.format(team_id=team_id_str)
    suspended_key = REDIS_SUSPENDED_KEY.format(team_id=team_id_str, provider=provider_name)
    budget_key = REDIS_BUDGET_KEY.format(team_id=team_id_str, provider=provider_name)
    window = int(time.time() // 60)
    rate_key = REDIS_RATE_KEY.format(team_id=team_id_str, provider=provider_name, window=window)

    # ── SINGLE Redis round trip ───────────────────────────────────────────────
    pipe = r.pipeline()
    pipe.get(ip_key)
    pipe.exists(suspended_key)
    pipe.hget(budget_key, 'spent')
    pipe.hget(budget_key, 'limit')
    pipe.incr(rate_key)
    pipe.expire(rate_key, 120)
    ip_raw, suspended_in_redis, spent_raw, limit_raw, rate_count, _ = pipe.execute()

    # ── Stage 1: IP Allowlist ─────────────────────────────────────────────────
    cidrs = json.loads(ip_raw) if ip_raw is not None else _load_ip_allowlist(team_id, r)
    if cidrs:
        client_ip = get_client_ip(request)
        if not _ip_in_cidrs(client_ip, cidrs):
            return PipelineResult(
                False, 'ip_blocked',
                f"Access denied: IP {client_ip} is not in the team's allowed range.",
            )

    # ── Stage 2a: Suspension check ────────────────────────────────────────────
    is_suspended = bool(suspended_in_redis) or provider_meta.get('is_suspended', False)
    if is_suspended:
        if not suspended_in_redis:
            r.set(suspended_key, '1')  # re-populate after Redis restart
        return PipelineResult(
            False, 'provider_suspended',
            f"Provider '{provider_name}' access suspended due to a security violation. "
            "Contact your TechLead.",
        )

    # ── Stage 2b: Budget check ────────────────────────────────────────────────
    if spent_raw is not None and limit_raw is not None:
        spent = float(spent_raw)
        limit = float(limit_raw)
    else:
        # Budget cache miss — seed from provider_meta (already from DB)
        spent = provider_meta['spent']
        limit = provider_meta['limit']
        bp = r.pipeline()
        bp.hset(budget_key, mapping={'spent': spent, 'limit': limit})
        bp.expire(budget_key, 30)
        bp.execute()

    if limit > 0 and spent >= limit:
        return PipelineResult(
            False, 'quota_exceeded',
            f"Quota exceeded for {provider_name}. Limit: ${limit:.4f}, Spent: ${spent:.4f}",
        )

    # ── Stage 2c: Rate limit ──────────────────────────────────────────────────
    rate_limit = provider_meta.get('rate_limit', 60)
    if rate_limit > 0 and rate_count > rate_limit:
        return PipelineResult(
            False, 'rate_limited',
            f"Rate limit exceeded for {provider_name}. Max {rate_limit} calls/min.",
        )

    # ── Stage 3: Prompt injection (pure Python) ───────────────────────────────
    text = _extract_prompt_text(body, provider_name)
    if text:
        matched = next((p for p in INJECTION_PATTERNS if p.search(text)), None)
        if matched:
            return _handle_injection(team_id, provider_meta, user, matched, r)

    return PipelineResult(True, None, None)


def _handle_injection(team_id, provider_meta: dict, user, matched_pattern, r) -> PipelineResult:
    provider_name = provider_meta['name']
    team_id_str = str(team_id)

    # Suspend in Redis (immediate) + DB (persistent) + invalidate meta cache
    pipe = r.pipeline()
    pipe.set(REDIS_SUSPENDED_KEY.format(team_id=team_id_str, provider=provider_name), '1')
    pipe.delete(REDIS_PROVIDER_KEY.format(team_id=team_id_str, provider=provider_name))
    pipe.execute()

    from apps.teams.models import TeamProvider, Team
    TeamProvider.objects.filter(pk=provider_meta['pk']).update(is_suspended=True)

    from apps.alerts.models import Alert
    team = Team.objects.get(pk=team_id)
    alert = Alert.objects.create(
        type='injection_blocked',
        severity='high',
        team=team,
        provider_name=provider_name,
        message=(
            f"SECURITY: Prompt injection detected from user '{user.email}' "
            f"targeting {provider_name}. "
            f"Provider access permanently suspended. "
            f"Pattern: {matched_pattern.pattern}"
        ),
    )
    publish_alert(r, alert)

    return PipelineResult(
        False, 'injection_blocked',
        f"Security violation: prompt injection detected. "
        f"Provider '{provider_name}' access permanently suspended.",
    )


# ── Post-LLM budget update ────────────────────────────────────────────────────

def update_budget_cache(team_id, provider_name: str, new_spent: float, limit: float, r) -> None:
    """Update Redis budget after successful LLM call with fresh DB value."""
    key = REDIS_BUDGET_KEY.format(team_id=str(team_id), provider=provider_name)
    pipe = r.pipeline()
    pipe.hset(key, mapping={'spent': new_spent, 'limit': limit})
    pipe.expire(key, 30)
    pipe.execute()
