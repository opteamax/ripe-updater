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
_DB_TAG_SLUG = 'ripe-database'
_DB_TAG_NAME = 'RIPE Database'
_DB_TAG_COLOR = '198754'  # Bootstrap green


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
        self.routes_created = 0
        self.routes_skipped = 0
        self.routes_errors = 0
        self.domains_created = 0
        self.domains_skipped = 0
        self.domains_errors = 0
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
            'routes_created': self.routes_created,
            'routes_skipped': self.routes_skipped,
            'routes_errors': self.routes_errors,
            'domains_created': self.domains_created,
            'domains_skipped': self.domains_skipped,
            'domains_errors': self.domains_errors,
        }

    def total_created(self):
        return (self.asns_created + self.aggregates_created + self.prefixes_created
                + self.routes_created + self.domains_created)

    def total_skipped(self):
        return (self.asns_skipped + self.aggregates_skipped + self.prefixes_skipped
                + self.routes_skipped + self.domains_skipped)

    def total_errors(self):
        return (self.asns_errors + self.aggregates_errors + self.prefixes_errors
                + self.routes_errors + self.domains_errors)


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

    # Tag applied to created objects (overridable by subclasses)
    tag_slug = _IMPORT_TAG_SLUG
    tag_name = _IMPORT_TAG_NAME
    tag_color = _IMPORT_TAG_COLOR
    tag_description = 'Imported from the RIPE LIR Portal My Resources API'

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
            data.get('number')
            or data.get('asn') or data.get('asnNumber') or data.get('asnId')
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
                slug=self.tag_slug,
                defaults={
                    'name': self.tag_name,
                    'color': self.tag_color,
                    'description': self.tag_description,
                },
            )
            if created:
                logger.info(f'Created tag: {self.tag_name}')
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


class RipeDbImporter(ResourceImporter):
    """Imports objects discovered in the RIPE Database via inverse lookups.

    Reuses the NetBox object helpers from :class:`ResourceImporter` but consumes
    the parsed-RPSL object shape produced by ``RipeDbSearchClient.get_all()``:

        inetnum / inet6num  → ipam.Aggregate (ALLOCATED*) or ipam.Prefix (other)
        route / route6      → netbox_ripe_sync.RipeRouteObject (+ Prefix link)

    Per the requirement, an inetnum/inet6num whose IP range is not yet present in
    NetBox is created; existing objects are left untouched and counted as skipped.
    """

    ALL_TYPES = ('inetnum', 'inet6num', 'route', 'route6', 'domain')

    tag_slug = _DB_TAG_SLUG
    tag_name = _DB_TAG_NAME
    tag_color = _DB_TAG_COLOR
    tag_description = 'Imported from the RIPE Database via inverse lookup'

    def run(self, objects=None):
        """Import objects from the dict returned by RipeDbSearchClient.get_all()."""
        if objects is None:
            from .ripe_db_client import RipeDbSearchClient
            objects = RipeDbSearchClient().get_all()

        for key in ('inetnum', 'inet6num'):
            if key in self.resource_types:
                for obj in objects.get(key, []):
                    self._safe_import_inetnum(obj, key)

        for key in ('route', 'route6'):
            if key in self.resource_types:
                for obj in objects.get(key, []):
                    self._safe_import_route(obj, key)

        if 'domain' in self.resource_types:
            for obj in objects.get('domain', []):
                self._safe_import_domain(obj)

        return self.stats

    # ------------------------------------------------------------------
    # Edit-state helpers (shared by all object types)
    # ------------------------------------------------------------------

    @staticmethod
    def _now():
        from django.utils import timezone
        return timezone.now()

    @staticmethod
    def _ripe_attr_list(attrs):
        """[(name, value)] -> [{'name': name, 'value': value}] for JSON storage."""
        return [{'name': k, 'value': v} for k, v in attrs]

    @staticmethod
    def _all(attrs, name):
        return [v for k, v in attrs if k == name]

    # ------------------------------------------------------------------
    # inetnum / inet6num
    # ------------------------------------------------------------------

    def _safe_import_inetnum(self, obj, object_type):
        attrs = obj.get('attributes', [])
        raw = self._first(attrs, object_type) or obj.get('primary_key', '')
        status = (self._first(attrs, 'status') or '').upper()
        netname = self._first(attrs, 'netname') or ''
        is_allocation = status.startswith('ALLOCATED')

        try:
            cidrs = self._to_cidrs(raw)
        except Exception as exc:
            logger.warning(f'{object_type} {raw!r}: cannot parse range — {exc}')
            # Attribute the error to the bucket it would have landed in.
            if is_allocation:
                self.stats.aggregates_errors += 1
                self.stats.errors.append(('aggregate', raw or '?', str(exc)))
            else:
                self.stats.prefixes_errors += 1
                self.stats.errors.append(('prefix', raw or '?', str(exc)))
            return

        for cidr in cidrs:
            data = {'prefix': cidr, 'status': status, 'netname': netname}
            if is_allocation:
                self._safe_import_aggregate(data, label=object_type)
            else:
                self._safe_import_prefix(data, label=object_type)

        # Maintain an editable RPSL mirror keyed by the original RIPE primary key.
        try:
            self._upsert_inetnum_mirror(object_type, raw, attrs, is_allocation, cidrs[0])
        except Exception as exc:
            logger.warning(f'{object_type} {raw}: could not store editable mirror — {exc}')

    def _upsert_inetnum_mirror(self, object_type, raw, attrs, is_allocation, first_cidr):
        from .config import get_config
        from .models import RipeInetnumObject

        if self.dry_run:
            return

        source = get_config('ripe_db')
        fields = dict(
            prefix=first_cidr,
            is_ipv6=(object_type == 'inet6num'),
            netname=self._first(attrs, 'netname') or '',
            description='\n'.join(self._all(attrs, 'descr')),
            country='\n'.join(self._all(attrs, 'country')),
            status=self._first(attrs, 'status') or '',
            org=self._first(attrs, 'org') or '',
            maintainer=self._first(attrs, 'mnt-by') or '',
            raw_attributes=self._ripe_attr_list(attrs),
            last_imported=self._now(),
        )

        from ipam.models import Aggregate, Prefix
        nb_prefix = None if is_allocation else Prefix.objects.filter(prefix=first_cidr).first()
        nb_aggregate = Aggregate.objects.filter(prefix=first_cidr).first() if is_allocation else None

        obj, created = RipeInetnumObject.objects.update_or_create(
            ripe_primary_key=raw, source=source,
            defaults=dict(
                netbox_prefix=nb_prefix,
                netbox_aggregate=nb_aggregate,
                **fields,
            ),
        )
        if created:
            obj.local_status = RipeInetnumObject.STATUS_IN_SYNC
            obj.save(update_fields=['local_status'])

    # ------------------------------------------------------------------
    # route / route6
    # ------------------------------------------------------------------

    def _safe_import_route(self, obj, object_type):
        attrs = obj.get('attributes', [])
        prefix_str = self._first(attrs, object_type) or ''
        origin = self._first(attrs, 'origin') or ''
        identifier = f'{prefix_str} {origin}'.strip()
        try:
            result = self._import_route(prefix_str, origin, attrs, object_type)
            logger.debug(f'Route {identifier} ({object_type}): {result}')
        except Exception as exc:
            logger.warning(f'Route {identifier} ({object_type}): error — {exc}')
            self.stats.routes_errors += 1
            self.stats.errors.append(('route', identifier or '?', str(exc)))

    def _import_route(self, prefix_str, origin, attrs, object_type):
        if not prefix_str:
            raise ValueError('Missing route prefix')
        if not origin:
            raise ValueError(f'Route {prefix_str} has no origin attribute')

        from .config import get_config
        from .models import RipeRouteObject

        source = get_config('ripe_db')
        descr = '\n'.join(self._all(attrs, 'descr'))
        maintainer = self._first(attrs, 'mnt-by') or ''
        existing = RipeRouteObject.objects.filter(
            prefix=prefix_str, origin=origin, source=source,
        ).first()

        if existing is not None:
            if not self.dry_run:
                # Refresh the last-known RIPE state (local edits live in changesets).
                existing.description = descr
                existing.maintainer = maintainer
                existing.raw_attributes = self._ripe_attr_list(attrs)
                existing.ripe_primary_key = f'{prefix_str}{origin}'
                existing.last_imported = self._now()
                self._link_prefix(existing, prefix_str)
                existing.save()
            self.stats.routes_skipped += 1
            return 'refreshed' if not self.dry_run else 'exists'

        if self.dry_run:
            self.stats.routes_created += 1
            return 'would_create'

        route = RipeRouteObject(
            prefix=prefix_str,
            origin=origin,
            is_ipv6=(object_type == 'route6'),
            maintainer=maintainer,
            source=source,
            description=descr,
            raw_attributes=self._ripe_attr_list(attrs),
            ripe_primary_key=f'{prefix_str}{origin}',
            last_imported=self._now(),
            local_status=RipeRouteObject.STATUS_IN_SYNC,
        )
        self._link_prefix(route, prefix_str)
        route.save()

        self.stats.routes_created += 1
        return 'created'

    @staticmethod
    def _link_prefix(obj, prefix_str):
        from ipam.models import Prefix
        nb_prefix = Prefix.objects.filter(prefix=prefix_str).first()
        if nb_prefix is not None:
            obj.netbox_prefix = nb_prefix

    # ------------------------------------------------------------------
    # domain
    # ------------------------------------------------------------------

    def _safe_import_domain(self, obj):
        attrs = obj.get('attributes', [])
        domain = self._first(attrs, 'domain') or obj.get('primary_key', '')
        try:
            result = self._import_domain(domain, attrs)
            logger.debug(f'Domain {domain}: {result}')
        except Exception as exc:
            logger.warning(f'Domain {domain}: error — {exc}')
            self.stats.domains_errors += 1
            self.stats.errors.append(('domain', domain or '?', str(exc)))

    def _import_domain(self, domain, attrs):
        if not domain:
            raise ValueError('Missing domain attribute')

        from .config import get_config
        from .models import RipeDomainObject

        source = get_config('ripe_db')
        fields = dict(
            description='\n'.join(self._all(attrs, 'descr')),
            admin_c=self._first(attrs, 'admin-c') or '',
            tech_c=self._first(attrs, 'tech-c') or '',
            zone_c=self._first(attrs, 'zone-c') or '',
            nameservers='\n'.join(self._all(attrs, 'nserver')),
            maintainer=self._first(attrs, 'mnt-by') or '',
            raw_attributes=self._ripe_attr_list(attrs),
            ripe_primary_key=domain,
            last_imported=self._now(),
        )

        existing = RipeDomainObject.objects.filter(domain=domain, source=source).first()
        if existing is not None:
            if not self.dry_run:
                for k, v in fields.items():
                    setattr(existing, k, v)
                existing.save()
            self.stats.domains_skipped += 1
            return 'refreshed' if not self.dry_run else 'exists'

        if self.dry_run:
            self.stats.domains_created += 1
            return 'would_create'

        RipeDomainObject.objects.create(
            domain=domain, source=source,
            local_status=RipeDomainObject.STATUS_IN_SYNC, **fields,
        )
        self.stats.domains_created += 1
        return 'created'

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _first(attrs, name):
        """Return the first value of attribute *name* from a [(name, value)] list."""
        for k, v in attrs:
            if k == name:
                return v
        return None

    @staticmethod
    def _to_cidrs(raw):
        """Convert a RIPE inetnum/inet6num key to a list of CIDR strings.

        IPv4 inetnum keys are ranges ('192.0.2.0 - 192.0.2.255') which may span
        more than one CIDR; inet6num keys are already CIDRs.
        """
        from ipaddress import ip_address, ip_network, summarize_address_range

        raw = (raw or '').strip()
        if not raw:
            raise ValueError('empty prefix value')
        if '-' in raw:
            start, end = (s.strip() for s in raw.split('-', 1))
            return [str(net) for net in summarize_address_range(ip_address(start), ip_address(end))]
        return [str(ip_network(raw, strict=False))]

    @staticmethod
    def _description(data):
        parts = ['Imported from RIPE Database']
        if data.get('netname'):
            parts.append(f"netname={data['netname']}")
        if data.get('status'):
            parts.append(f"status={data['status']}")
        return ' | '.join(parts)
