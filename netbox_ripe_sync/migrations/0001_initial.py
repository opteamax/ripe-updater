import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='RipeSyncLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('prefix', models.CharField(db_index=True, max_length=50)),
                ('action', models.CharField(
                    choices=[('create', 'Create'), ('update', 'Update'), ('delete', 'Delete')],
                    max_length=20,
                )),
                ('status', models.CharField(
                    choices=[('success', 'Success'), ('failed', 'Failed'), ('skipped', 'Skipped')],
                    max_length=20,
                )),
                ('triggered_by', models.CharField(blank=True, max_length=150)),
                ('ripe_response', models.TextField(blank=True)),
                ('error_message', models.TextField(blank=True)),
                ('created', models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                'ordering': ['-created'],
                'app_label': 'netbox_ripe_sync',
            },
        ),
    ]
