"""Management command to import resources from the RIPE LIR Portal My Resources API.

Runs synchronously in the current process (no RQ worker needed).

Examples:
    python manage.py ripe_import_resources
    python manage.py ripe_import_resources --dry-run
    python manage.py ripe_import_resources --only asns ipv4_allocations
"""

from django.core.management.base import BaseCommand, CommandError

from ...importer import ResourceImporter
from ...my_resources_client import MyResourcesClient, MyResourcesError


class Command(BaseCommand):
    help = 'Import ASNs, allocations, and assignments from the RIPE My Resources API into NetBox.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be imported without making any changes.',
        )
        parser.add_argument(
            '--only',
            nargs='+',
            metavar='TYPE',
            choices=ResourceImporter.ALL_TYPES,
            help=(
                'Import only the listed resource type(s). '
                f'Choices: {", ".join(ResourceImporter.ALL_TYPES)}'
            ),
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        resource_types = options.get('only') or None

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — no changes will be made.\n'))

        self.stdout.write('Fetching resources from RIPE LIR Portal My Resources API…')
        try:
            client = MyResourcesClient()
            resources = client.get_all()
        except MyResourcesError as exc:
            raise CommandError(str(exc)) from exc

        # Print a summary of what was fetched
        for key, items in resources.items():
            self.stdout.write(f'  {key}: {len(items)} item(s) fetched')

        self.stdout.write('\nImporting into NetBox…')
        importer = ResourceImporter(dry_run=dry_run, resource_types=resource_types)
        stats = importer.run(resources)

        verb = 'Would create' if dry_run else 'Created'

        self.stdout.write('\nResults:')
        self.stdout.write(f'  ASNs       — {verb}: {stats.asns_created}, skipped: {stats.asns_skipped}, errors: {stats.asns_errors}')
        self.stdout.write(f'  Aggregates — {verb}: {stats.aggregates_created}, skipped: {stats.aggregates_skipped}, errors: {stats.aggregates_errors}')
        self.stdout.write(f'  Prefixes   — {verb}: {stats.prefixes_created}, skipped: {stats.prefixes_skipped}, errors: {stats.prefixes_errors}')
        self.stdout.write(
            f'\nTotal — {verb}: {stats.total_created()}, '
            f'skipped: {stats.total_skipped()}, '
            f'errors: {stats.total_errors()}'
        )

        if stats.errors:
            self.stdout.write(self.style.WARNING('\nErrors:'))
            for resource_type, identifier, message in stats.errors:
                self.stdout.write(f'  [{resource_type}] {identifier}: {message}')

        if stats.total_errors() == 0:
            self.stdout.write(self.style.SUCCESS('\nImport complete.'))
        else:
            self.stdout.write(self.style.WARNING('\nImport complete with errors (see above).'))
