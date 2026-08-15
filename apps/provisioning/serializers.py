from rest_framework import serializers
from .models import ProvisioningTask


class OnboardSerializer(serializers.Serializer):
    email = serializers.EmailField()
    team_id = serializers.UUIDField(required=False, allow_null=True)
    role = serializers.ChoiceField(
        choices=['TECHLEAD', 'PARTLEAD', 'MEMBER', 'DEVOPS'],
        required=False,
        default='MEMBER'
    )


class OffboardSerializer(serializers.Serializer):
    email = serializers.EmailField()
    figma_transfer_to = serializers.EmailField(required=False, allow_null=True, allow_blank=True)


class ProvisioningTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProvisioningTask
        fields = [
            'task_id', 'email', 'figma_transfer_to',
            'task_type', 'status', 'steps',
            'created_at', 'updated_at',
        ]
        read_only_fields = fields


class ProvisioningResponseSerializer(serializers.Serializer):
    task_id = serializers.UUIDField()
    status = serializers.CharField()
