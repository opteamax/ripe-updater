import django_tables2 as tables

from .models import RipeSyncLog


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
