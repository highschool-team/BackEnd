import httpx
from django.conf import settings
from config.celery import app


@app.task(bind=True, max_retries=3, default_retry_delay=5)
def send_slack_alert(self, alert_payload: dict):
    """Alert를 Slack Incoming Webhook으로 전송."""
    webhook_url = getattr(settings, 'SLACK_WEBHOOK_URL', '')
    if not webhook_url:
        return  # Slack 미설정 시 조용히 스킵

    # severity별 emoji
    severity_emoji = {'high': '🚨', 'medium': '⚠️', 'low': 'ℹ️'}
    type_label = {
        'injection_blocked': '프롬프트 인젝션 차단',
        'quota_warning': '예산 경고',
        'blocked': '팀 차단',
        'ip_blocked': 'IP 차단',
        'rate_limited': '속도 제한',
    }

    emoji = severity_emoji.get(alert_payload.get('severity', 'low'), 'ℹ️')
    label = type_label.get(alert_payload.get('type', ''), alert_payload.get('type', ''))

    payload = {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} FinOps Guard - {label}",
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*팀*\n{alert_payload.get('team_name', '-')}"},
                    {"type": "mrkdwn", "text": f"*프로바이더*\n{alert_payload.get('provider_name', '-')}"},
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*메시지*\n{alert_payload.get('message', '')}",
                },
            },
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"발생 시각: {alert_payload.get('created_at', '')}"},
                ],
            },
        ]
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(webhook_url, json=payload)
            resp.raise_for_status()
    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        raise self.retry(exc=exc)
