import django_tables2 as tables

from .models import RipeSyncLog, RipeImportRun


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
        fields = ('id', 'started', 'finished', 'status', 'dry_run', 'triggered_by', 'created', 'skipped', 'errors')
        attrs = {'class': 'table table-hover table-sm'}
        empty_text = 'No import runs found.'
        order_by = '-started'
