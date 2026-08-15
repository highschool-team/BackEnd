import ipaddress
from decimal import Decimal
from rest_framework import serializers
from .models import Team, TeamProvider, TeamIPAllowlist
from common.constants import PROVIDER_CONFIG


class TeamProviderSerializer(serializers.ModelSerializer):
    color = serializers.CharField(read_only=True)
    allowed_models = serializers.ListField(read_only=True)

    class Meta:
        model = TeamProvider
        fields = [
            'id', 'name', 'limit', 'spent',
            'selected_model', 'color', 'allowed_models',
            'rate_limit', 'is_suspended',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'spent', 'is_suspended', 'created_at', 'updated_at']


class TeamIPAllowlistSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeamIPAllowlist
        fields = ['id', 'ip_cidr', 'description', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate_ip_cidr(self, value):
        try:
            ipaddress.ip_network(value, strict=False)
        except ValueError:
            raise serializers.ValidationError(f"'{value}' is not a valid IP or CIDR range.")
        return value


class ProviderRateLimitSerializer(serializers.Serializer):
    rate_limit = serializers.IntegerField(min_value=0, max_value=10000)


class TeamSerializer(serializers.ModelSerializer):
    providers = TeamProviderSerializer(many=True, read_only=True)
    spent = serializers.DecimalField(max_digits=12, decimal_places=4, read_only=True)
    allocated = serializers.DecimalField(max_digits=12, decimal_places=4, read_only=True)
    member_count = serializers.SerializerMethodField()

    class Meta:
        model = Team
        fields = [
            'id', 'name', 'budget', 'status',
            'spent', 'allocated', 'providers',
            'member_count', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'status', 'spent', 'allocated', 'created_at', 'updated_at']

    def get_member_count(self, obj):
        return obj.members.count()


class TeamBudgetSerializer(serializers.Serializer):
    budget = serializers.DecimalField(max_digits=12, decimal_places=4, min_value=Decimal('0'))


class AddProviderSerializer(serializers.Serializer):
    name = serializers.ChoiceField(choices=list(PROVIDER_CONFIG.keys()))

    def validate_name(self, value):
        team = self.context.get('team')
        if team and team.providers.filter(name=value).exists():
            raise serializers.ValidationError(f"Provider '{value}' already exists for this team.")
        return value


class ProviderLimitSerializer(serializers.Serializer):
    limit = serializers.DecimalField(max_digits=12, decimal_places=4, min_value=Decimal('0'))


class ProviderModelSerializer(serializers.Serializer):
    model = serializers.CharField()

    def validate_model(self, value):
        provider_name = self.context.get('provider_name')
        if provider_name:
            config = PROVIDER_CONFIG.get(provider_name, {})
            allowed = config.get('allowed_models', [])
            if value not in allowed:
                raise serializers.ValidationError(
                    f"Model '{value}' is not allowed. Allowed models: {allowed}"
                )
        return value
