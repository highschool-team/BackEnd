from rest_framework import serializers
from .models import UsageLog


class UsageLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = UsageLog
        fields = [
            'id', 'user', 'team', 'provider_name', 'model_name',
            'cost', 'input_tokens', 'output_tokens', 'created_at',
        ]
        read_only_fields = fields


class TeamUsageSummarySerializer(serializers.Serializer):
    team_id = serializers.UUIDField()
    team_name = serializers.CharField()
    budget = serializers.DecimalField(max_digits=12, decimal_places=4)
    spent = serializers.DecimalField(max_digits=12, decimal_places=4)
    allocated = serializers.DecimalField(max_digits=12, decimal_places=4)
    status = serializers.CharField()


class DashboardOverviewSerializer(serializers.Serializer):
    company_budget = serializers.DecimalField(max_digits=14, decimal_places=4)
    total_spent = serializers.DecimalField(max_digits=14, decimal_places=4)
    total_allocated = serializers.DecimalField(max_digits=14, decimal_places=4)
    blocked_teams = serializers.IntegerField()
    teams_summary = TeamUsageSummarySerializer(many=True)


class MemberUsageSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()
    email = serializers.EmailField()
    total_cost = serializers.DecimalField(max_digits=12, decimal_places=6)
    total_calls = serializers.IntegerField()
    total_input_tokens = serializers.IntegerField()
    total_output_tokens = serializers.IntegerField()
