import json

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

from common.constants import REDIS_JWT_BLACKLIST_PREFIX, REDIS_VKEY_PREFIX
from common.redis_client import get_redis


class VirtualAPIKeyAuthentication(BaseAuthentication):
    """Authenticates requests using an X-Api-Key header with a fng_ prefixed key."""

    def authenticate(self, request):
        key = request.META.get('HTTP_X_API_KEY', '')
        if not key.startswith('fng_'):
            return None  # Not this authenticator — pass to next

        r = get_redis()
        cache_key = f"{REDIS_VKEY_PREFIX}{key}"
        cached = r.get(cache_key)

        if cached:
            data = json.loads(cached)
            from .models import User
            try:
                user = User.objects.get(pk=data['user_id'])
                return (user, key)
            except User.DoesNotExist:
                r.delete(cache_key)
                raise AuthenticationFailed('Invalid API key.')

        # DB fallback
        from .models import VirtualAPIKey
        try:
            vkey = VirtualAPIKey.objects.select_related('user').get(key=key, is_active=True)
        except VirtualAPIKey.DoesNotExist:
            raise AuthenticationFailed('Invalid or inactive API key.')

        # Cache for 300 seconds
        r.setex(cache_key, 300, json.dumps({
            'user_id': str(vkey.user.id),
            'team_id': str(vkey.user.team_id) if vkey.user.team_id else None,
        }))

        # Update last_used_at with minimal performance impact
        from django.utils import timezone
        VirtualAPIKey.objects.filter(pk=vkey.pk).update(last_used_at=timezone.now())

        return (vkey.user, vkey)


class RedisBlacklistJWTAuthentication(JWTAuthentication):
    """JWT authentication that checks a Redis blacklist before validating."""

    def get_validated_token(self, raw_token):
        token = super().get_validated_token(raw_token)
        jti = token.get('jti')
        if jti:
            if get_redis().exists(f"{REDIS_JWT_BLACKLIST_PREFIX}{jti}"):
                raise AuthenticationFailed('Token has been blacklisted.')
        return token
