import uuid
from django.db import models


class Alert(models.Model):
    TYPE_CHOICES = [
        ('quota_warning', 'Quota Warning'),
        ('blocked', 'Blocked'),
        ('injection_blocked', 'Injection Blocked'),
        ('ip_blocked', 'IP Blocked'),
        ('rate_limited', 'Rate Limited'),
    ]

    SEVERITY_CHOICES = [
        ('high', 'High'),
        ('medium', 'Medium'),
        ('low', 'Low'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type = models.CharField(max_length=50, choices=TYPE_CHOICES)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='medium')
    team = models.ForeignKey(
        'teams.Team',
        on_delete=models.CASCADE,
        related_name='alerts',
    )
    provider_name = models.CharField(max_length=100)
    message = models.TextField()
    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'alerts'
        verbose_name = 'Alert'
        verbose_name_plural = 'Alerts'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['team', 'read', 'created_at']),
            models.Index(fields=['severity', 'created_at']),
        ]

    def __str__(self):
        return f"{self.type} - {self.team.name} - {self.provider_name}"
