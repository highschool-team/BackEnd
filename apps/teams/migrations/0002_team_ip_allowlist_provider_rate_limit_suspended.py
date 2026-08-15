import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('teams', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='teamprovider',
            name='rate_limit',
            field=models.IntegerField(default=60),
        ),
        migrations.AddField(
            model_name='teamprovider',
            name='is_suspended',
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name='TeamIPAllowlist',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('ip_cidr', models.CharField(max_length=50)),
                ('description', models.CharField(blank=True, max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('team', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='ip_allowlist',
                    to='teams.team',
                )),
            ],
            options={
                'verbose_name': 'Team IP Allowlist',
                'verbose_name_plural': 'Team IP Allowlists',
                'db_table': 'team_ip_allowlist',
                'unique_together': {('team', 'ip_cidr')},
            },
        ),
    ]
