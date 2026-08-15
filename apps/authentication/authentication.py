from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed

from common.constants import REDIS_JWT_BLACKLIST_PREFIX
from common.redis_client import get_redis


class RedisBlacklistJWTAuthentication(JWTAuthentication):
    """JWT authentication that checks a Redis blacklist before validating."""

    def get_validated_token(self, raw_token):
        token = super().get_validated_token(raw_token)
        jti = token.get('jti')
        if jti:
            if get_redis().exists(f"{REDIS_JWT_BLACKLIST_PREFIX}{jti}"):
                raise AuthenticationFailed('Token has been blacklisted.')
        return token
