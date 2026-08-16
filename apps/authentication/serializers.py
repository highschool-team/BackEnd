from rest_framework import serializers
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User, VirtualAPIKey


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')

        user = authenticate(request=self.context.get('request'), username=email, password=password)
        if not user:
            raise serializers.ValidationError('Invalid email or password.')
        if not user.is_active:
            raise serializers.ValidationError('User account is disabled.')

        attrs['user'] = user
        return attrs


class UserSerializer(serializers.ModelSerializer):
    team_id = serializers.UUIDField(source='team.id', read_only=True, allow_null=True)

    class Meta:
        model = User
        fields = ['id', 'email', 'role', 'team_id']


class TokenResponseSerializer(serializers.Serializer):
    access_token = serializers.CharField()
    refresh_token = serializers.CharField()
    user = UserSerializer()


class RefreshTokenSerializer(serializers.Serializer):
    refresh_token = serializers.CharField()


class VirtualAPIKeySerializer(serializers.ModelSerializer):
    class Meta:
        model = VirtualAPIKey
        fields = ['id', 'name', 'key', 'created_at', 'last_used_at', 'is_active']
        read_only_fields = ['id', 'key', 'created_at', 'last_used_at']


class CreateVirtualAPIKeySerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100, default='Default Key')
