from rest_framework import serializers
from .models import Alert


class AlertSerializer(serializers.ModelSerializer):
    team_name = serializers.CharField(source='team.name', read_only=True)

    class Meta:
        model = Alert
        fields = [
            'id', 'type', 'severity', 'team', 'team_name',
            'provider_name', 'message', 'read', 'created_at',
        ]
        read_only_fields = ['id', 'team_name', 'created_at']
