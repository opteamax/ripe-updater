from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('netbox_ripe_sync', '0004_edit_and_push'),
    ]

    operations = [
        migrations.AlterField(
            model_name='ripesynclog',
            name='status',
            field=models.CharField(
                choices=[
                    ('success', 'Success'),
                    ('failed', 'Failed'),
                    ('skipped', 'Skipped'),
                    ('queued', 'Queued for review'),
                ],
                max_length=20,
            ),
        ),
    ]
