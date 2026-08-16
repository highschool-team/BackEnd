import time
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken
from rest_framework_simplejwt.exceptions import TokenError

from common.constants import REDIS_JWT_BLACKLIST_PREFIX, REDIS_VKEY_PREFIX
from common.redis_client import get_redis
from .models import VirtualAPIKey
from .serializers import (
    LoginSerializer,
    UserSerializer,
    RefreshTokenSerializer,
    TokenResponseSerializer,
    VirtualAPIKeySerializer,
    CreateVirtualAPIKeySerializer,
)


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


class VirtualAPIKeyView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='가상 API 키 목록 조회',
        responses={200: VirtualAPIKeySerializer(many=True)},
        tags=['API Keys'],
    )
    def get(self, request):
        keys = VirtualAPIKey.objects.filter(user=request.user, is_active=True)
        serializer = VirtualAPIKeySerializer(keys, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary='가상 API 키 생성',
        request=CreateVirtualAPIKeySerializer,
        responses={201: VirtualAPIKeySerializer},
        tags=['API Keys'],
    )
    def post(self, request):
        serializer = CreateVirtualAPIKeySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        vkey = VirtualAPIKey.objects.create(
            user=request.user,
            name=serializer.validated_data.get('name', 'Default Key'),
            key=VirtualAPIKey.generate_key(),
        )
        return Response(VirtualAPIKeySerializer(vkey).data, status=status.HTTP_201_CREATED)


class VirtualAPIKeyDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='가상 API 키 비활성화',
        responses={
            200: {'type': 'object', 'properties': {'message': {'type': 'string'}}},
            404: {'type': 'object', 'properties': {'error': {'type': 'string'}}},
        },
        tags=['API Keys'],
    )
    def delete(self, request, pk):
        try:
            vkey = VirtualAPIKey.objects.get(pk=pk, user=request.user)
        except VirtualAPIKey.DoesNotExist:
            return Response(
                {'error': 'API key not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Deactivate and remove from Redis cache
        vkey.is_active = False
        vkey.save(update_fields=['is_active'])

        r = get_redis()
        r.delete(f"{REDIS_VKEY_PREFIX}{vkey.key}")

        return Response({'message': 'API key deactivated.'}, status=status.HTTP_200_OK)
