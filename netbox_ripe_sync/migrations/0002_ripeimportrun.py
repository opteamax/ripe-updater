from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('netbox_ripe_sync', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='RipeImportRun',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('started', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('finished', models.DateTimeField(blank=True, null=True)),
                ('status', models.CharField(
                    choices=[
                        ('running', 'Running'),
                        ('success', 'Success'),
                        ('failed', 'Failed'),
                    ],
                    default='running',
                    max_length=20,
                )),
                ('triggered_by', models.CharField(blank=True, max_length=150)),
                ('dry_run', models.BooleanField(default=False)),
                ('asns_created', models.IntegerField(default=0)),
                ('asns_skipped', models.IntegerField(default=0)),
                ('asns_errors', models.IntegerField(default=0)),
                ('aggregates_created', models.IntegerField(default=0)),
                ('aggregates_skipped', models.IntegerField(default=0)),
                ('aggregates_errors', models.IntegerField(default=0)),
                ('prefixes_created', models.IntegerField(default=0)),
                ('prefixes_skipped', models.IntegerField(default=0)),
                ('prefixes_errors', models.IntegerField(default=0)),
                ('error_message', models.TextField(blank=True)),
                ('error_detail', models.TextField(blank=True)),
            ],
            options={
                'ordering': ['-started'],
                'app_label': 'netbox_ripe_sync',
            },
        ),
    ]
