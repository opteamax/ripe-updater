"""Management command to create the NetBox custom fields required by netbox_ripe_sync."""

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        'Create the three custom fields required by netbox_ripe_sync: '
        'ripe_report (Prefix), ripe_template (Prefix), lir (Aggregate).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Re-apply label / description updates to existing fields.',
        )

    def handle(self, *args, **options):
        try:
            from extras.models import CustomField
        except ImportError:
            raise CommandError('Could not import extras.models.CustomField — is NetBox installed?')

        from django.contrib.contenttypes.models import ContentType
        from ipam.models import Aggregate, Prefix

        prefix_ct = ContentType.objects.get_for_model(Prefix)
        aggregate_ct = ContentType.objects.get_for_model(Aggregate)
        force = options['force']

        self._ensure_field(
            name='ripe_report',
            defaults={
                'label': 'RIPE Report',
                'type': 'boolean',
                'description': 'Enable RIPE Database synchronisation for this prefix.',
                'required': False,
            },
            content_type=prefix_ct,
            force=force,
        )

        self._ensure_field(
            name='ripe_template',
            defaults={
                'label': 'RIPE Template',
                'type': 'text',
                'description': (
                    'Template key (uppercase) from templates.json, '
                    'e.g. CLOUD-POOL or INFRA-TRANSFER-NET.'
                ),
                'required': False,
            },
            content_type=prefix_ct,
            force=force,
        )

        self._ensure_field(
            name='lir',
            defaults={
                'label': 'LIR',
                'type': 'text',
                'description': (
                    'RIPE Local Internet Registry slug (lowercase) '
                    'matching a key in lir_org.json, e.g. de.examplelir1.'
                ),
                'required': False,
            },
            content_type=aggregate_ct,
            force=force,
        )

        self.stdout.write(self.style.SUCCESS('\nSetup complete. Custom fields are ready.'))
        self.stdout.write(
            'Next steps:\n'
            '  1. Populate lir_org.json and templates.json in your templates_dir.\n'
            '  2. Set ripe_report=True and ripe_template on the prefixes you want to sync.\n'
            '  3. Set lir on each aggregate.\n'
            '  4. Start the RQ worker: python manage.py rqworker default\n'
        )

    def _ensure_field(self, name, defaults, content_type, force):
        from extras.models import CustomField

        cf, created = CustomField.objects.get_or_create(name=name, defaults=defaults)

        if not created and force:
            for key, value in defaults.items():
                setattr(cf, key, value)
            cf.save()
            self.stdout.write(f'  Updated  custom field: {name}')
        elif created:
            self.stdout.write(f'  Created  custom field: {name}')
        else:
            self.stdout.write(f'  Exists   custom field: {name} (use --force to update)')

        # Attach to the correct model if not already
        if content_type not in cf.content_types.all():
            cf.content_types.add(content_type)
            self.stdout.write(f'           → attached to {content_type.app_label}.{content_type.model}')
