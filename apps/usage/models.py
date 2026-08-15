import uuid
from django.db import models
from django.conf import settings


class UsageLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='usage_logs',
    )
    team = models.ForeignKey(
        'teams.Team',
        on_delete=models.CASCADE,
        related_name='usage_logs',
    )
    provider_name = models.CharField(max_length=100)
    model_name = models.CharField(max_length=255)
    cost = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    input_tokens = models.IntegerField(default=0)
    output_tokens = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'usage_logs'
        verbose_name = 'Usage Log'
        verbose_name_plural = 'Usage Logs'
        indexes = [
            models.Index(fields=['team', 'created_at']),
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['provider_name', 'created_at']),
        ]

    def __str__(self):
        return f"{self.team} - {self.provider_name} - {self.model_name} @ {self.created_at}"
