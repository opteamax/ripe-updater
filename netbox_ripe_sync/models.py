import json

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


class RipeSyncLog(models.Model):
    ACTION_CREATE = 'create'
    ACTION_UPDATE = 'update'
    ACTION_DELETE = 'delete'
    ACTION_CHOICES = [
        (ACTION_CREATE, 'Create'),
        (ACTION_UPDATE, 'Update'),
        (ACTION_DELETE, 'Delete'),
    ]

    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_SKIPPED = 'skipped'
    STATUS_QUEUED = 'queued'
    STATUS_CHOICES = [
        (STATUS_SUCCESS, 'Success'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_SKIPPED, 'Skipped'),
        (STATUS_QUEUED, 'Queued for review'),
    ]

    prefix = models.CharField(max_length=50, db_index=True)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    triggered_by = models.CharField(max_length=150, blank=True)
    ripe_response = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    created = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        app_label = 'netbox_ripe_sync'
        ordering = ['-created']

    def __str__(self):
        return f'{self.prefix} {self.action} ({self.status}) @ {self.created:%Y-%m-%d %H:%M}'

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('plugins:netbox_ripe_sync:ripesyncclog', args=[self.pk])

    @property
    def status_badge(self):
        return {
            self.STATUS_SUCCESS: 'success',
            self.STATUS_FAILED: 'danger',
            self.STATUS_SKIPPED: 'warning',
            self.STATUS_QUEUED: 'info',
        }.get(self.status, 'secondary')


class RipeImportRun(models.Model):
    """Records one complete run of an import job (My Resources or RIPE Database)."""

    STATUS_RUNNING = 'running'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_RUNNING, 'Running'),
        (STATUS_SUCCESS, 'Success'),
        (STATUS_FAILED, 'Failed'),
    ]

    SOURCE_MY_RESOURCES = 'my_resources'
    SOURCE_RIPE_DB = 'ripe_db'
    SOURCE_CHOICES = [
        (SOURCE_MY_RESOURCES, 'LIR Portal My Resources'),
        (SOURCE_RIPE_DB, 'RIPE Database'),
    ]

    started = models.DateTimeField(auto_now_add=True, db_index=True)
    finished = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_RUNNING)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default=SOURCE_MY_RESOURCES)
    triggered_by = models.CharField(max_length=150, blank=True)
    dry_run = models.BooleanField(default=False)

    # Per-type counters
    asns_created = models.IntegerField(default=0)
    asns_skipped = models.IntegerField(default=0)
    asns_errors = models.IntegerField(default=0)
    aggregates_created = models.IntegerField(default=0)
    aggregates_skipped = models.IntegerField(default=0)
    aggregates_errors = models.IntegerField(default=0)
    prefixes_created = models.IntegerField(default=0)
    prefixes_skipped = models.IntegerField(default=0)
    prefixes_errors = models.IntegerField(default=0)
    routes_created = models.IntegerField(default=0)
    routes_skipped = models.IntegerField(default=0)
    routes_errors = models.IntegerField(default=0)
    domains_created = models.IntegerField(default=0)
    domains_skipped = models.IntegerField(default=0)
    domains_errors = models.IntegerField(default=0)

    error_message = models.TextField(blank=True)
    # JSON array of (resource_type, identifier, message) tuples for per-resource errors
    error_detail = models.TextField(blank=True)

    class Meta:
        app_label = 'netbox_ripe_sync'
        ordering = ['-started']

    def __str__(self):
        ts = self.started.strftime('%Y-%m-%d %H:%M')
        label = '[DRY RUN] ' if self.dry_run else ''
        return f'{label}Import run {ts} ({self.status})'

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('plugins:netbox_ripe_sync:ripeimportrun', args=[self.pk])

    @property
    def status_badge(self):
        return {
            self.STATUS_RUNNING: 'info',
            self.STATUS_SUCCESS: 'success',
            self.STATUS_FAILED: 'danger',
        }.get(self.status, 'secondary')

    def total_created(self):
        return (self.asns_created + self.aggregates_created + self.prefixes_created
                + self.routes_created + self.domains_created)

    def total_skipped(self):
        return (self.asns_skipped + self.aggregates_skipped + self.prefixes_skipped
                + self.routes_skipped + self.domains_skipped)

    def total_errors(self):
        return (self.asns_errors + self.aggregates_errors + self.prefixes_errors
                + self.routes_errors + self.domains_errors)

    def get_error_detail(self):
        if not self.error_detail:
            return []
        try:
            return json.loads(self.error_detail)
        except (ValueError, TypeError):
            return []


class ManagedRipeObjectMixin:
    """Shared edit-state behaviour for locally-stored, editable RIPE objects.

    Concrete models declare the actual fields (``raw_attributes``,
    ``local_status`` …) plus the type-specific structured fields; this mixin
    only contributes the constants and helper methods so they stay in one place.

    ``object_type`` (e.g. 'inetnum', 'route6', 'domain') must be provided by each
    concrete model, either as an attribute or a property.
    """

    STATUS_IN_SYNC = 'in_sync'
    STATUS_LOCAL = 'local'            # created locally, not yet in RIPE
    STATUS_PUSH_FAILED = 'push_failed'
    STATUS_CHOICES = [
        (STATUS_IN_SYNC, 'In sync'),
        (STATUS_LOCAL, 'Local only'),
        (STATUS_PUSH_FAILED, 'Push failed'),
    ]

    object_type = ''  # overridden by concrete models

    def pending_changes(self):
        ct = ContentType.objects.get_for_model(self.__class__)
        return RipeChange.objects.filter(
            content_type=ct, object_id=self.pk, status=RipeChange.STATUS_PENDING,
        )

    @property
    def has_pending(self):
        return self.pending_changes().exists()

    @property
    def status_badge(self):
        return {
            self.STATUS_IN_SYNC: 'success',
            self.STATUS_LOCAL: 'info',
            self.STATUS_PUSH_FAILED: 'danger',
        }.get(self.local_status, 'secondary')


class RipeRouteObject(ManagedRipeObjectMixin, models.Model):
    """A route / route6 object imported from the RIPE Database.

    NetBox has no native representation for RPSL route objects, which describe a
    (prefix, origin-AS) routing intent.  This model captures them so they remain
    visible, editable and queryable in NetBox, optionally linked to the Prefix.
    """

    prefix = models.CharField(max_length=50, db_index=True)
    origin = models.CharField(max_length=20, db_index=True, help_text='Origin AS, e.g. AS64500')
    is_ipv6 = models.BooleanField(default=False)
    maintainer = models.CharField(max_length=100, blank=True)
    source = models.CharField(max_length=20, blank=True, help_text='RIPE / TEST')
    description = models.TextField(blank=True)
    netbox_prefix = models.ForeignKey(
        'ipam.Prefix',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
    )
    # Edit-state (see ManagedRipeObjectMixin)
    ripe_primary_key = models.CharField(max_length=200, blank=True)
    raw_attributes = models.JSONField(default=list, blank=True)
    local_status = models.CharField(
        max_length=20, choices=ManagedRipeObjectMixin.STATUS_CHOICES,
        default=ManagedRipeObjectMixin.STATUS_IN_SYNC,
    )
    last_imported = models.DateTimeField(null=True, blank=True)
    last_pushed = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    created = models.DateTimeField(auto_now_add=True, db_index=True)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'netbox_ripe_sync'
        ordering = ['prefix', 'origin']
        unique_together = [('prefix', 'origin', 'source')]

    @property
    def object_type(self):
        return 'route6' if self.is_ipv6 else 'route'

    def __str__(self):
        return f'{self.prefix} → {self.origin}'

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('plugins:netbox_ripe_sync:riperouteobject', args=[self.pk])


class RipeDomainObject(ManagedRipeObjectMixin, models.Model):
    """A reverse-DNS ``domain`` object imported from the RIPE Database."""

    domain = models.CharField(max_length=255, db_index=True, help_text='e.g. 2.0.192.in-addr.arpa')
    description = models.TextField(blank=True)
    admin_c = models.CharField(max_length=100, blank=True)
    tech_c = models.CharField(max_length=100, blank=True)
    zone_c = models.CharField(max_length=100, blank=True)
    # One nameserver per line.
    nameservers = models.TextField(blank=True)
    maintainer = models.CharField(max_length=100, blank=True)
    source = models.CharField(max_length=20, blank=True, help_text='RIPE / TEST')
    # Edit-state
    ripe_primary_key = models.CharField(max_length=255, blank=True)
    raw_attributes = models.JSONField(default=list, blank=True)
    local_status = models.CharField(
        max_length=20, choices=ManagedRipeObjectMixin.STATUS_CHOICES,
        default=ManagedRipeObjectMixin.STATUS_IN_SYNC,
    )
    last_imported = models.DateTimeField(null=True, blank=True)
    last_pushed = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    created = models.DateTimeField(auto_now_add=True, db_index=True)
    last_updated = models.DateTimeField(auto_now=True)

    object_type = 'domain'

    class Meta:
        app_label = 'netbox_ripe_sync'
        ordering = ['domain']
        unique_together = [('domain', 'source')]

    def nameserver_list(self):
        return [n.strip() for n in self.nameservers.splitlines() if n.strip()]

    def __str__(self):
        return self.domain

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('plugins:netbox_ripe_sync:ripedomainobject', args=[self.pk])


class RipeInetnumObject(ManagedRipeObjectMixin, models.Model):
    """An editable mirror of a RIPE ``inetnum`` / ``inet6num`` object.

    The importer also creates an ``ipam.Aggregate``/``ipam.Prefix`` for the IP
    range; this model holds the RPSL attributes so the object can be edited and
    pushed back to the RIPE Database directly (bypassing the template engine).
    """

    prefix = models.CharField(max_length=80, db_index=True,
                              help_text='CIDR or RIPE range, as stored in RIPE')
    is_ipv6 = models.BooleanField(default=False)
    netname = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    country = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=50, blank=True)
    org = models.CharField(max_length=100, blank=True)
    netbox_prefix = models.ForeignKey(
        'ipam.Prefix', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    netbox_aggregate = models.ForeignKey(
        'ipam.Aggregate', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    maintainer = models.CharField(max_length=100, blank=True)
    source = models.CharField(max_length=20, blank=True, help_text='RIPE / TEST')
    # Edit-state
    ripe_primary_key = models.CharField(max_length=80, blank=True)
    raw_attributes = models.JSONField(default=list, blank=True)
    local_status = models.CharField(
        max_length=20, choices=ManagedRipeObjectMixin.STATUS_CHOICES,
        default=ManagedRipeObjectMixin.STATUS_IN_SYNC,
    )
    last_imported = models.DateTimeField(null=True, blank=True)
    last_pushed = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    created = models.DateTimeField(auto_now_add=True, db_index=True)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'netbox_ripe_sync'
        ordering = ['prefix']
        unique_together = [('ripe_primary_key', 'source')]

    @property
    def object_type(self):
        return 'inet6num' if self.is_ipv6 else 'inetnum'

    def __str__(self):
        return self.prefix

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('plugins:netbox_ripe_sync:ripeinetnumobject', args=[self.pk])


class RipeChange(models.Model):
    """A pending or completed change to a RIPE object, queued for push.

    Edits made in NetBox never touch RIPE directly — they accumulate here as
    ``pending`` changes.  Pushing requires an explicit, separate confirmation
    which transitions the change to ``pushed`` (or ``failed``).
    """

    OP_CREATE = 'create'
    OP_MODIFY = 'modify'
    OP_DELETE = 'delete'
    OP_CHOICES = [
        (OP_CREATE, 'Create'),
        (OP_MODIFY, 'Modify'),
        (OP_DELETE, 'Delete'),
    ]

    STATUS_PENDING = 'pending'
    STATUS_PUSHED = 'pushed'
    STATUS_FAILED = 'failed'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PUSHED, 'Pushed'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField()
    target = GenericForeignKey('content_type', 'object_id')

    object_type = models.CharField(max_length=20)
    primary_key = models.CharField(max_length=255)
    operation = models.CharField(max_length=10, choices=OP_CHOICES, default=OP_MODIFY)
    # Full RPSL attribute list to push: [{"name": .., "value": ..}, ...]
    proposed_attributes = models.JSONField(default=list, blank=True)
    # Human-readable diff vs the last-known RIPE state.
    diff = models.TextField(blank=True)

    status = models.CharField(max_length=12, choices=STATUS_CHOICES,
                              default=STATUS_PENDING, db_index=True)
    requested_by = models.CharField(max_length=150, blank=True)
    requested_at = models.DateTimeField(auto_now_add=True, db_index=True)
    pushed_by = models.CharField(max_length=150, blank=True)
    pushed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    ripe_response = models.TextField(blank=True)

    class Meta:
        app_label = 'netbox_ripe_sync'
        ordering = ['-requested_at']

    def __str__(self):
        return f'{self.get_operation_display()} {self.object_type} {self.primary_key} ({self.status})'

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('plugins:netbox_ripe_sync:ripechange', args=[self.pk])

    @property
    def status_badge(self):
        return {
            self.STATUS_PENDING: 'warning',
            self.STATUS_PUSHED: 'success',
            self.STATUS_FAILED: 'danger',
            self.STATUS_CANCELLED: 'secondary',
        }.get(self.status, 'secondary')

    def get_diff_lines(self):
        if not self.diff:
            return []
        return self.diff.splitlines()
