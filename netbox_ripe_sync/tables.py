import django_tables2 as tables

from .models import (
    RipeSyncLog,
    RipeImportRun,
    RipeRouteObject,
    RipeDomainObject,
    RipeInetnumObject,
    RipeChange,
)


def _status_badge_col():
    return tables.TemplateColumn(
        template_code=(
            '<span class="badge bg-{{ record.status_badge }}">'
            '{{ record.get_local_status_display }}</span>'
        ),
        accessor='local_status',
        verbose_name='State',
    )


class RipeSyncLogTable(tables.Table):
    prefix = tables.Column()
    action = tables.Column()
    status = tables.TemplateColumn(
        template_code=(
            '<span class="badge bg-{{ record.status_badge }}">'
            '{{ record.get_status_display }}</span>'
        ),
        orderable=True,
    )
    triggered_by = tables.Column(verbose_name='Triggered by')
    ripe_response = tables.Column(verbose_name='Response', orderable=False)
    error_message = tables.Column(verbose_name='Error', orderable=False)
    created = tables.DateTimeColumn(format='Y-m-d H:i:s')

    class Meta:
        model = RipeSyncLog
        fields = ('created', 'prefix', 'action', 'status', 'triggered_by', 'ripe_response', 'error_message')
        attrs = {'class': 'table table-hover table-sm'}
        empty_text = 'No RIPE sync logs found.'
        order_by = '-created'


class RipeImportRunTable(tables.Table):
    id = tables.Column(
        linkify=lambda record: record.get_absolute_url(),
        verbose_name='Run #',
    )
    started = tables.DateTimeColumn(format='Y-m-d H:i:s')
    finished = tables.DateTimeColumn(format='Y-m-d H:i:s')
    source = tables.Column(accessor='get_source_display', verbose_name='Source', orderable=True)
    status = tables.TemplateColumn(
        template_code=(
            '<span class="badge bg-{{ record.status_badge }}">'
            '{{ record.get_status_display }}</span>'
        ),
    )
    dry_run = tables.BooleanColumn()
    triggered_by = tables.Column(verbose_name='Triggered by')
    created = tables.Column(
        accessor='total_created',
        verbose_name='Created',
        orderable=False,
    )
    skipped = tables.Column(
        accessor='total_skipped',
        verbose_name='Skipped',
        orderable=False,
    )
    errors = tables.Column(
        accessor='total_errors',
        verbose_name='Errors',
        orderable=False,
    )

    class Meta:
        model = RipeImportRun
        fields = ('id', 'started', 'finished', 'source', 'status', 'dry_run', 'triggered_by', 'created', 'skipped', 'errors')
        attrs = {'class': 'table table-hover table-sm'}
        empty_text = 'No import runs found.'
        order_by = '-started'


class RipeRouteObjectTable(tables.Table):
    prefix = tables.Column(linkify=lambda record: record.get_absolute_url())
    origin = tables.Column()
    is_ipv6 = tables.BooleanColumn(verbose_name='IPv6')
    maintainer = tables.Column()
    source = tables.Column()
    netbox_prefix = tables.Column(
        linkify=lambda record: record.netbox_prefix.get_absolute_url() if record.netbox_prefix else None,
        verbose_name='NetBox Prefix',
    )
    state = _status_badge_col()
    created = tables.DateTimeColumn(format='Y-m-d H:i:s')

    class Meta:
        model = RipeRouteObject
        fields = ('prefix', 'origin', 'is_ipv6', 'maintainer', 'source', 'netbox_prefix', 'state', 'created')
        attrs = {'class': 'table table-hover table-sm'}
        empty_text = 'No RIPE route objects imported yet.'
        order_by = 'prefix'


class RipeDomainObjectTable(tables.Table):
    domain = tables.Column(linkify=lambda record: record.get_absolute_url())
    maintainer = tables.Column()
    source = tables.Column()
    state = _status_badge_col()
    created = tables.DateTimeColumn(format='Y-m-d H:i:s')

    class Meta:
        model = RipeDomainObject
        fields = ('domain', 'maintainer', 'source', 'state', 'created')
        attrs = {'class': 'table table-hover table-sm'}
        empty_text = 'No RIPE domain objects imported yet.'
        order_by = 'domain'


class RipeInetnumObjectTable(tables.Table):
    prefix = tables.Column(linkify=lambda record: record.get_absolute_url())
    netname = tables.Column()
    status = tables.Column()
    is_ipv6 = tables.BooleanColumn(verbose_name='IPv6')
    maintainer = tables.Column()
    source = tables.Column()
    state = _status_badge_col()

    class Meta:
        model = RipeInetnumObject
        fields = ('prefix', 'netname', 'status', 'is_ipv6', 'maintainer', 'source', 'state')
        attrs = {'class': 'table table-hover table-sm'}
        empty_text = 'No RIPE inetnum objects imported yet.'
        order_by = 'prefix'


class RipeChangeTable(tables.Table):
    id = tables.Column(linkify=lambda record: record.get_absolute_url(), verbose_name='Change #')
    operation = tables.Column(accessor='get_operation_display', verbose_name='Operation')
    object_type = tables.Column(verbose_name='Type')
    primary_key = tables.Column(verbose_name='Object')
    status = tables.TemplateColumn(
        template_code=(
            '<span class="badge bg-{{ record.status_badge }}">'
            '{{ record.get_status_display }}</span>'
        ),
    )
    requested_by = tables.Column(verbose_name='Requested by')
    requested_at = tables.DateTimeColumn(format='Y-m-d H:i:s')

    class Meta:
        model = RipeChange
        fields = ('id', 'operation', 'object_type', 'primary_key', 'status', 'requested_by', 'requested_at')
        attrs = {'class': 'table table-hover table-sm'}
        empty_text = 'No changes queued.'
        order_by = '-requested_at'
