from netbox.plugins import PluginTemplateExtension

from .models import RipeSyncLog


class PrefixRipeSyncPanel(PluginTemplateExtension):
    models = ['ipam.prefix']

    def right_page(self):
        prefix = self.context['object']
        recent_logs = RipeSyncLog.objects.filter(
            prefix=str(prefix.prefix)
        ).order_by('-created')[:5]

        return self.render(
            'netbox_ripe_sync/inc/prefix_panel.html',
            extra_context={
                'recent_logs': recent_logs,
                'ripe_report': bool(prefix.custom_field_data.get('ripe_report')),
            },
        )


template_extensions = [PrefixRipeSyncPanel]
