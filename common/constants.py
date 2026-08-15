PROVIDER_CONFIG = {
    "OpenAI": {
        "color": "#10a37f",
        "allowed_models": ["GPT-4o", "GPT-4o-mini", "o3-mini"],
        "api_base": "https://api.openai.com",
        "api_key_env": "OPENAI_API_KEY",
        "header_key": "Authorization",
        "header_prefix": "Bearer",
    },
    "Anthropic": {
        "color": "#d97757",
        "allowed_models": ["Claude Opus 4.7", "Claude Sonnet 4.6", "Claude Haiku 4.5"],
        "api_base": "https://api.anthropic.com",
        "api_key_env": "ANTHROPIC_API_KEY",
        "header_key": "x-api-key",
        "header_prefix": "",
    },
    "Gemini": {
        "color": "#4285f4",
        "allowed_models": ["Gemini 1.5 Pro", "Gemini 1.5 Flash", "Gemini 2.0 Flash"],
        "api_base": "https://generativelanguage.googleapis.com",
        "api_key_env": "GEMINI_API_KEY",
        "header_key": "X-Goog-Api-Key",
        "header_prefix": "",
    },
}

# Cost per 1K tokens (input/output) in USD
TOKEN_COST_CONFIG = {
    "GPT-4o": {"input": 0.005, "output": 0.015},
    "GPT-4o-mini": {"input": 0.00015, "output": 0.0006},
    "o3-mini": {"input": 0.001, "output": 0.004},
    "Claude Opus 4.7": {"input": 0.015, "output": 0.075},
    "Claude Sonnet 4.6": {"input": 0.003, "output": 0.015},
    "Claude Haiku 4.5": {"input": 0.00025, "output": 0.00125},
    "Gemini 1.5 Pro": {"input": 0.00125, "output": 0.005},
    "Gemini 1.5 Flash": {"input": 0.000075, "output": 0.0003},
    "Gemini 2.0 Flash": {"input": 0.0001, "output": 0.0004},
}

# Redis channel names
REDIS_ALERTS_CHANNEL = 'finops:alerts'
REDIS_PROVISIONING_CHANNEL_PREFIX = 'finops:provisioning:'
REDIS_TASK_KEY_PREFIX = 'finops:task:'
REDIS_JWT_BLACKLIST_PREFIX = 'finops:jwt:blacklist:'

# Redis pipeline keys (format strings)
REDIS_IP_ALLOWLIST_KEY = 'finops:ip:allowlist:{team_id}'
REDIS_BUDGET_KEY = 'finops:budget:{team_id}:{provider}'
REDIS_RATE_KEY = 'finops:rate:{team_id}:{provider}:{window}'
REDIS_SUSPENDED_KEY = 'finops:suspended:{team_id}:{provider}'
REDIS_PROVIDER_KEY = 'finops:provider:{team_id}:{provider}'

# Provisioning steps
PROVISIONING_STEPS = ["Google Workspace", "Slack", "Figma", "GitHub", "Notion"]

# Alert thresholds
QUOTA_WARNING_THRESHOLD = 0.80  # 80%
QUOTA_BLOCKED_THRESHOLD = 1.00  # 100%

# Prompt injection detection patterns (compiled regexes)
import re

INJECTION_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'ignore\s+(all\s+)?(previous|prior|above)\s+instructions',
        r'forget\s+(all\s+)?(previous|prior|above)\s+instructions',
        r'disregard\s+(all\s+)?(previous|prior|above)',
        r'override\s+(your|all)\s+(instructions|guidelines|rules|constraints)',
        r'pretend\s+(you\s+are|to\s+be)',
        r'\bjailbreak\b',
        r'\bdan\s+mode\b',
        r'\bdeveloper\s+mode\b',
        r'do\s+anything\s+now',
        r'bypass\s+(your|the)\s+(restrictions|rules|guidelines|filters|safety)',
        r'ignore\s+(your|the)\s+(restrictions|rules|guidelines|filters|safety)',
        r'<\|im_start\|>\s*system',
        r'prompt\s+injection',
    ]
]
