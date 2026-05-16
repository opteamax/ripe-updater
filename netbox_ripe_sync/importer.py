"""Import RIPE My Resources data into NetBox.

Mapping:
    ASNs                       → ipam.ASN
    IPv4/IPv6 Allocations      → ipam.Aggregate  (LIR-held blocks)
    IPv4/IPv6 Assignments      → ipam.Prefix      (end-user assignments)
    IPv4 Legacy (ERX)          → ipam.Aggregate

Existing objects are never overwritten — the importer skips them and reports
them as 'skipped'.  Resources created by the importer are tagged
'ripe-my-resources' so users can identify and manage them.
"""

import datetime
import logging

from .my_resources_client import MyResourcesClient

logger = logging.getLogger('netbox.plugins.ripe_sync')

_RIPE_RIR_SLUG = 'ripe-ncc'
_RIPE_RIR_NAME = 'RIPE NCC'
_IMPORT_TAG_SLUG = 'ripe-my-resources'
_IMPORT_TAG_NAME = 'RIPE My Resources'
_IMPORT_TAG_COLOR = '0d6efd'  # Bootstrap blue


class ImportStats:
    def __init__(self):
        self.asns_created = 0
        self.asns_skipped = 0
        self.asns_errors = 0
        self.aggregates_created = 0
        self.aggregates_skipped = 0
        self.aggregates_errors = 0
        self.prefixes_created = 0
        self.prefixes_skipped = 0
        self.prefixes_errors = 0
        self.errors = []  # list of (resource_type, identifier, message)

    def as_dict(self):
        return {
            'asns_created': self.asns_created,
            'asns_skipped': self.asns_skipped,
            'asns_errors': self.asns_errors,
            'aggregates_created': self.aggregates_created,
            'aggregates_skipped': self.aggregates_skipped,
            'aggregates_errors': self.aggregates_errors,
            'prefixes_created': self.prefixes_created,
            'prefixes_skipped': self.prefixes_skipped,
            'prefixes_errors': self.prefixes_errors,
        }

    def total_created(self):
        return self.asns_created + self.aggregates_created + self.prefixes_created

    def total_skipped(self):
        return self.asns_skipped + self.aggregates_skipped + self.prefixes_skipped

    def total_errors(self):
        return self.asns_errors + self.aggregates_errors + self.prefixes_errors


class ResourceImporter:
    """Imports resources from the My Resources API into NetBox.

    Args:
        dry_run: When True, no NetBox objects are created or modified.
                 Logs and stats still reflect what *would* happen.
        resource_types: Iterable of resource category names to import.
                        None means import all.
    """

    ALL_TYPES = (
        'asns',
        'ipv4_allocations',
        'ipv4_assignments',
        'ipv4_legacy',
        'ipv6_allocations',
        'ipv6_assignments',
    )

    def __init__(self, dry_run=False, resource_types=None):
        self.dry_run = dry_run
        self.resource_types = set(resource_types) if resource_types else set(self.ALL_TYPES)
        self.stats = ImportStats()
        self._rir = None
        self._tag = None

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run(self, resources=None):
        """Import all resource types from the dict returned by MyResourcesClient.get_all().

        If *resources* is None, a fresh API call is made.
        """
        if resources is None:
            client = MyResourcesClient()
            resources = client.get_all()

        if 'asns' in self.resource_types:
            for item in resources.get('asns', []):
                self._safe_import_asn(item)

        for key in ('ipv4_allocations', 'ipv4_legacy', 'ipv6_allocations'):
            if key in self.resource_types:
                for item in resources.get(key, []):
                    self._safe_import_aggregate(item, label=key)

        for key in ('ipv4_assignments', 'ipv6_assignments'):
            if key in self.resource_types:
                for item in resources.get(key, []):
                    self._safe_import_prefix(item, label=key)

        return self.stats

    # ------------------------------------------------------------------
    # Per-type importers
    # ------------------------------------------------------------------

    def _safe_import_asn(self, data):
        # _asn_int is set by MyResourcesClient.get_asns() after range expansion
        asn_int = data.get('_asn_int') or MyResourcesClient.parse_asn_number(
            data.get('asn') or data.get('asnNumber') or data.get('asnId')
            or data.get('startAsn')
        )
        identifier = f'AS{asn_int}' if asn_int else repr(data)
        try:
            result = self._import_asn(asn_int, data)
            logger.debug(f'ASN {identifier}: {result}')
        except Exception as exc:
            logger.warning(f'ASN {identifier}: error — {exc}')
            self.stats.asns_errors += 1
            self.stats.errors.append(('asn', identifier, str(exc)))

    def _import_asn(self, asn_int, data):
        if asn_int is None:
            raise ValueError(f'Cannot parse ASN number from {data!r}')

        from ipam.models import ASN
        if ASN.objects.filter(asn=asn_int).exists():
            self.stats.asns_skipped += 1
            return 'skipped'

        if self.dry_run:
            self.stats.asns_created += 1
            return 'would_create'

        obj = ASN(
            asn=asn_int,
            rir=self._get_rir(),
            description=self._description(data),
        )
        obj.save()
        obj.tags.add(self._get_tag())
        self.stats.asns_created += 1
        return 'created'

    def _safe_import_aggregate(self, data, label):
        prefix_str = data.get('prefix')
        try:
            result = self._import_aggregate(prefix_str, data)
            logger.debug(f'Aggregate {prefix_str} ({label}): {result}')
        except Exception as exc:
            logger.warning(f'Aggregate {prefix_str} ({label}): error — {exc}')
            self.stats.aggregates_errors += 1
            self.stats.errors.append(('aggregate', prefix_str or '?', str(exc)))

    def _import_aggregate(self, prefix_str, data):
        if not prefix_str:
            raise ValueError('Missing prefix field')

        from ipam.models import Aggregate
        if Aggregate.objects.filter(prefix=prefix_str).exists():
            self.stats.aggregates_skipped += 1
            return 'skipped'

        if self.dry_run:
            self.stats.aggregates_created += 1
            return 'would_create'

        obj = Aggregate(
            prefix=prefix_str,
            rir=self._get_rir(),
            date_added=self._parse_date(data.get('registrationDate')),
            description=self._description(data),
        )
        obj.save()
        obj.tags.add(self._get_tag())
        self.stats.aggregates_created += 1
        return 'created'

    def _safe_import_prefix(self, data, label):
        prefix_str = data.get('prefix')
        try:
            result = self._import_prefix(prefix_str, data)
            logger.debug(f'Prefix {prefix_str} ({label}): {result}')
        except Exception as exc:
            logger.warning(f'Prefix {prefix_str} ({label}): error — {exc}')
            self.stats.prefixes_errors += 1
            self.stats.errors.append(('prefix', prefix_str or '?', str(exc)))

    def _import_prefix(self, prefix_str, data):
        if not prefix_str:
            raise ValueError('Missing prefix field')

        from ipam.models import Prefix
        if Prefix.objects.filter(prefix=prefix_str).exists():
            self.stats.prefixes_skipped += 1
            return 'skipped'

        if self.dry_run:
            self.stats.prefixes_created += 1
            return 'would_create'

        obj = Prefix(
            prefix=prefix_str,
            status='active',
            description=self._description(data),
        )
        obj.save()
        obj.tags.add(self._get_tag())
        self.stats.prefixes_created += 1
        return 'created'

    # ------------------------------------------------------------------
    # Shared NetBox object helpers
    # ------------------------------------------------------------------

    def _get_rir(self):
        if self._rir is None:
            from ipam.models import RIR
            self._rir, created = RIR.objects.get_or_create(
                slug=_RIPE_RIR_SLUG,
                defaults={'name': _RIPE_RIR_NAME, 'is_private': False},
            )
            if created:
                logger.info(f'Created RIR: {_RIPE_RIR_NAME}')
        return self._rir

    def _get_tag(self):
        if self._tag is None:
            from extras.models import Tag
            self._tag, created = Tag.objects.get_or_create(
                slug=_IMPORT_TAG_SLUG,
                defaults={
                    'name': _IMPORT_TAG_NAME,
                    'color': _IMPORT_TAG_COLOR,
                    'description': 'Imported from the RIPE LIR Portal My Resources API',
                },
            )
            if created:
                logger.info(f'Created tag: {_IMPORT_TAG_NAME}')
        return self._tag

    # ------------------------------------------------------------------
    # Data conversion helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_date(raw):
        if not raw:
            return None
        try:
            return datetime.date.fromisoformat(str(raw))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _description(data):
        status = data.get('status', '')
        ticket = (data.get('ticket') or {}).get('ticketNumber', '')
        parts = ['Imported from RIPE My Resources API']
        if status:
            parts.append(f'status={status}')
        if ticket:
            parts.append(f'ticket={ticket}')
        return ' | '.join(parts)
