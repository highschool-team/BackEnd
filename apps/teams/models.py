import uuid
from decimal import Decimal
from django.db import models

from common.constants import PROVIDER_CONFIG


class Team(models.Model):
    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('BLOCKED', 'Blocked'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, unique=True)
    budget = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal('0.0000'))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'teams'
        verbose_name = 'Team'
        verbose_name_plural = 'Teams'

    def __str__(self):
        return self.name

    @property
    def spent(self):
        """Sum of all TeamProvider.spent values for this team."""
        result = self.providers.aggregate(total=models.Sum('spent'))
        return result['total'] or Decimal('0.0000')

    @property
    def allocated(self):
        """Sum of all TeamProvider.limit values for this team."""
        result = self.providers.aggregate(total=models.Sum('limit'))
        return result['total'] or Decimal('0.0000')


class TeamProvider(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='providers')
    name = models.CharField(max_length=100)  # Provider name e.g. "OpenAI"
    limit = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal('10.0000'))
    spent = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal('0.0000'))
    selected_model = models.CharField(max_length=255, null=True, blank=True)
    rate_limit = models.IntegerField(default=60)  # max calls per minute, 0 = unlimited
    is_suspended = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'team_providers'
        unique_together = ('team', 'name')
        verbose_name = 'Team Provider'
        verbose_name_plural = 'Team Providers'

    def __str__(self):
        return f"{self.team.name} - {self.name}"

    @property
    def color(self):
        config = PROVIDER_CONFIG.get(self.name, {})
        return config.get('color', '#000000')

    @property
    def allowed_models(self):
        config = PROVIDER_CONFIG.get(self.name, {})
        return config.get('allowed_models', [])


class TeamIPAllowlist(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='ip_allowlist')
    ip_cidr = models.CharField(max_length=50)  # e.g. "192.168.1.0/24" or "10.0.0.1/32"
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'team_ip_allowlist'
        unique_together = ('team', 'ip_cidr')
        verbose_name = 'Team IP Allowlist'
        verbose_name_plural = 'Team IP Allowlists'

    def __str__(self):
        return f"{self.team.name} - {self.ip_cidr}"
