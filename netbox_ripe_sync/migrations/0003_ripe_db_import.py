import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ipam', '0001_initial'),
        ('netbox_ripe_sync', '0002_ripeimportrun'),
    ]

    operations = [
        migrations.AddField(
            model_name='ripeimportrun',
            name='source',
            field=models.CharField(
                choices=[
                    ('my_resources', 'LIR Portal My Resources'),
                    ('ripe_db', 'RIPE Database'),
                ],
                default='my_resources',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='ripeimportrun',
            name='routes_created',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='ripeimportrun',
            name='routes_skipped',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='ripeimportrun',
            name='routes_errors',
            field=models.IntegerField(default=0),
        ),
        migrations.CreateModel(
            name='RipeRouteObject',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('prefix', models.CharField(db_index=True, max_length=50)),
                ('origin', models.CharField(db_index=True, help_text='Origin AS, e.g. AS64500', max_length=20)),
                ('is_ipv6', models.BooleanField(default=False)),
                ('maintainer', models.CharField(blank=True, max_length=100)),
                ('source', models.CharField(blank=True, help_text='RIPE / TEST', max_length=20)),
                ('description', models.TextField(blank=True)),
                ('created', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('last_updated', models.DateTimeField(auto_now=True)),
                ('netbox_prefix', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+',
                    to='ipam.prefix',
                )),
            ],
            options={
                'ordering': ['prefix', 'origin'],
                'app_label': 'netbox_ripe_sync',
                'unique_together': {('prefix', 'origin', 'source')},
            },
        ),
    ]
