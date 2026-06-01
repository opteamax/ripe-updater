import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        ('ipam', '0001_initial'),
        ('netbox_ripe_sync', '0003_ripe_db_import'),
    ]

    _STATUS_CHOICES = [
        ('in_sync', 'In sync'),
        ('local', 'Local only'),
        ('push_failed', 'Push failed'),
    ]

    operations = [
        # --- Domain counters on the import run ---
        migrations.AddField(
            model_name='ripeimportrun',
            name='domains_created',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='ripeimportrun',
            name='domains_skipped',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='ripeimportrun',
            name='domains_errors',
            field=models.IntegerField(default=0),
        ),
        # --- Edit-state fields on the existing route object ---
        migrations.AddField(
            model_name='riperouteobject',
            name='ripe_primary_key',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name='riperouteobject',
            name='raw_attributes',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='riperouteobject',
            name='local_status',
            field=models.CharField(choices=_STATUS_CHOICES, default='in_sync', max_length=20),
        ),
        migrations.AddField(
            model_name='riperouteobject',
            name='last_imported',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='riperouteobject',
            name='last_pushed',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='riperouteobject',
            name='last_error',
            field=models.TextField(blank=True),
        ),
        # --- Domain objects ---
        migrations.CreateModel(
            name='RipeDomainObject',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('domain', models.CharField(db_index=True, help_text='e.g. 2.0.192.in-addr.arpa', max_length=255)),
                ('description', models.TextField(blank=True)),
                ('admin_c', models.CharField(blank=True, max_length=100)),
                ('tech_c', models.CharField(blank=True, max_length=100)),
                ('zone_c', models.CharField(blank=True, max_length=100)),
                ('nameservers', models.TextField(blank=True)),
                ('maintainer', models.CharField(blank=True, max_length=100)),
                ('source', models.CharField(blank=True, help_text='RIPE / TEST', max_length=20)),
                ('ripe_primary_key', models.CharField(blank=True, max_length=255)),
                ('raw_attributes', models.JSONField(blank=True, default=list)),
                ('local_status', models.CharField(choices=_STATUS_CHOICES, default='in_sync', max_length=20)),
                ('last_imported', models.DateTimeField(blank=True, null=True)),
                ('last_pushed', models.DateTimeField(blank=True, null=True)),
                ('last_error', models.TextField(blank=True)),
                ('created', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('last_updated', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['domain'],
                'app_label': 'netbox_ripe_sync',
                'unique_together': {('domain', 'source')},
            },
        ),
        # --- Inetnum / inet6num editable mirror ---
        migrations.CreateModel(
            name='RipeInetnumObject',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('prefix', models.CharField(db_index=True, help_text='CIDR or RIPE range, as stored in RIPE', max_length=80)),
                ('is_ipv6', models.BooleanField(default=False)),
                ('netname', models.CharField(blank=True, max_length=100)),
                ('description', models.TextField(blank=True)),
                ('country', models.CharField(blank=True, max_length=100)),
                ('status', models.CharField(blank=True, max_length=50)),
                ('org', models.CharField(blank=True, max_length=100)),
                ('maintainer', models.CharField(blank=True, max_length=100)),
                ('source', models.CharField(blank=True, help_text='RIPE / TEST', max_length=20)),
                ('ripe_primary_key', models.CharField(blank=True, max_length=80)),
                ('raw_attributes', models.JSONField(blank=True, default=list)),
                ('local_status', models.CharField(choices=_STATUS_CHOICES, default='in_sync', max_length=20)),
                ('last_imported', models.DateTimeField(blank=True, null=True)),
                ('last_pushed', models.DateTimeField(blank=True, null=True)),
                ('last_error', models.TextField(blank=True)),
                ('created', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('last_updated', models.DateTimeField(auto_now=True)),
                ('netbox_prefix', models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+', to='ipam.prefix')),
                ('netbox_aggregate', models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+', to='ipam.aggregate')),
            ],
            options={
                'ordering': ['prefix'],
                'app_label': 'netbox_ripe_sync',
                'unique_together': {('ripe_primary_key', 'source')},
            },
        ),
        # --- Changeset queue ---
        migrations.CreateModel(
            name='RipeChange',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('object_id', models.PositiveBigIntegerField()),
                ('object_type', models.CharField(max_length=20)),
                ('primary_key', models.CharField(max_length=255)),
                ('operation', models.CharField(
                    choices=[('create', 'Create'), ('modify', 'Modify'), ('delete', 'Delete')],
                    default='modify', max_length=10)),
                ('proposed_attributes', models.JSONField(blank=True, default=list)),
                ('diff', models.TextField(blank=True)),
                ('status', models.CharField(
                    choices=[
                        ('pending', 'Pending'),
                        ('pushed', 'Pushed'),
                        ('failed', 'Failed'),
                        ('cancelled', 'Cancelled'),
                    ],
                    db_index=True, default='pending', max_length=12)),
                ('requested_by', models.CharField(blank=True, max_length=150)),
                ('requested_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('pushed_by', models.CharField(blank=True, max_length=150)),
                ('pushed_at', models.DateTimeField(blank=True, null=True)),
                ('error_message', models.TextField(blank=True)),
                ('ripe_response', models.TextField(blank=True)),
                ('content_type', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE, to='contenttypes.contenttype')),
            ],
            options={
                'ordering': ['-requested_at'],
                'app_label': 'netbox_ripe_sync',
            },
        ),
    ]
