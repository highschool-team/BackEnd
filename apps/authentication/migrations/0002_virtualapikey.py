# Generated manually on 2026-08-15

import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='VirtualAPIKey',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('key', models.CharField(max_length=68, unique=True)),
                ('name', models.CharField(default='Default Key', max_length=100)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('last_used_at', models.DateTimeField(blank=True, null=True)),
                ('is_active', models.BooleanField(default=True)),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='api_keys',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'db_table': 'virtual_api_keys',
                'ordering': ['-created_at'],
            },
        ),
    ]
