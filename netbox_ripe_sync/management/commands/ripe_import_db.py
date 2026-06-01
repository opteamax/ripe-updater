"""Management command to import objects from the RIPE Database via inverse lookup.

Discovers inetnum/inet6num/route/route6 objects maintained by the configured
maintainers (ripe_db_maintainers) and/or organisations (ripe_db_orgs) and imports
them into NetBox.  Runs synchronously (no RQ worker needed).

Examples:
    python manage.py ripe_import_db
    python manage.py ripe_import_db --dry-run
    python manage.py ripe_import_db --only inetnum route
"""

from django.core.management.base import BaseCommand, CommandError

from ...importer import RipeDbImporter
from ...ripe_db_client import RipeDbSearchClient, RipeDbSearchError


class Command(BaseCommand):
    help = 'Import inetnum/inet6num/route/route6 objects from the RIPE Database into NetBox.'

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
            choices=RipeDbImporter.ALL_TYPES,
            help=(
                'Import only the listed object type(s). '
                f'Choices: {", ".join(RipeDbImporter.ALL_TYPES)}'
            ),
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        object_types = options.get('only') or None

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — no changes will be made.\n'))

        self.stdout.write('Querying the RIPE Database via inverse lookup…')
        try:
            client = RipeDbSearchClient()
            objects = client.get_all(object_types=object_types)
        except RipeDbSearchError as exc:
            raise CommandError(str(exc)) from exc
        except Exception as exc:
            raise CommandError(f'{type(exc).__name__}: {exc}') from exc

        for key, items in objects.items():
            self.stdout.write(f'  {key}: {len(items)} object(s) discovered')

        self.stdout.write('\nImporting into NetBox…')
        importer = RipeDbImporter(dry_run=dry_run, resource_types=object_types)
        stats = importer.run(objects)

        verb = 'Would create' if dry_run else 'Created'

        self.stdout.write('\nResults:')
        self.stdout.write(f'  Aggregates — {verb}: {stats.aggregates_created}, skipped: {stats.aggregates_skipped}, errors: {stats.aggregates_errors}')
        self.stdout.write(f'  Prefixes   — {verb}: {stats.prefixes_created}, skipped: {stats.prefixes_skipped}, errors: {stats.prefixes_errors}')
        self.stdout.write(f'  Routes     — {verb}: {stats.routes_created}, skipped: {stats.routes_skipped}, errors: {stats.routes_errors}')
        self.stdout.write(f'  Domains    — {verb}: {stats.domains_created}, skipped: {stats.domains_skipped}, errors: {stats.domains_errors}')
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
