import uuid
from django.db import models


class ProvisioningTask(models.Model):
    TASK_TYPE_CHOICES = [
        ('onboard', 'Onboard'),
        ('offboard', 'Offboard'),
    ]

    STATUS_CHOICES = [
        ('processing', 'Processing'),
        ('done', 'Done'),
        ('failed', 'Failed'),
    ]

    task_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField()
    figma_transfer_to = models.EmailField(null=True, blank=True)
    task_type = models.CharField(max_length=20, choices=TASK_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='processing')
    steps = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'provisioning_tasks'
        verbose_name = 'Provisioning Task'
        verbose_name_plural = 'Provisioning Tasks'

    def __str__(self):
        return f"{self.task_type} - {self.email} - {self.status}"
