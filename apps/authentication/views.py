import time
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken
from rest_framework_simplejwt.exceptions import TokenError

from common.constants import REDIS_JWT_BLACKLIST_PREFIX
from common.redis_client import get_redis
from .serializers import LoginSerializer, UserSerializer, RefreshTokenSerializer, TokenResponseSerializer


class LoginView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        summary='로그인',
        request=LoginSerializer,
        responses={200: TokenResponseSerializer},
        tags=['Auth'],
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data['user']
        refresh = RefreshToken.for_user(user)
        access = refresh.access_token

        return Response({
            'access_token': str(access),
            'refresh_token': str(refresh),
            'user': UserSerializer(user).data,
        }, status=status.HTTP_200_OK)


class RefreshView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        summary='액세스 토큰 재발급',
        request=RefreshTokenSerializer,
        responses={200: {'type': 'object', 'properties': {'access_token': {'type': 'string'}}}},
        tags=['Auth'],
    )
    def post(self, request):
        serializer = RefreshTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            refresh = RefreshToken(serializer.validated_data['refresh_token'])
            new_access = refresh.access_token
        except TokenError as e:
            return Response(
                {'error': 'invalid_token', 'message': str(e)},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        return Response({'access_token': str(new_access)}, status=status.HTTP_200_OK)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='로그아웃 (토큰 블랙리스트 등록)',
        request=None,
        responses={200: {'type': 'object', 'properties': {'message': {'type': 'string'}}}},
        tags=['Auth'],
    )
    def post(self, request):
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.startswith('Bearer '):
            return Response(
                {'error': 'missing_token', 'message': 'Authorization header is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        raw_token = auth_header.split(' ', 1)[1]

        try:
            token = AccessToken(raw_token)
            jti = token.get('jti')
            exp = token.get('exp')

            if not jti:
                return Response(
                    {'error': 'invalid_token', 'message': 'Token has no JTI claim.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            r = get_redis()
            ttl = int(exp - time.time())
            if ttl > 0:
                r.setex(f"{REDIS_JWT_BLACKLIST_PREFIX}{jti}", ttl, '1')

        except TokenError as e:
            return Response(
                {'error': 'invalid_token', 'message': str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({'message': 'Successfully logged out.'}, status=status.HTTP_200_OK)
