from netbox.plugins.navigation import PluginMenu, PluginMenuItem

menu = PluginMenu(
    label='RIPE Sync',
    groups=(
        ('', (
            PluginMenuItem(
                link='plugins:netbox_ripe_sync:ripesyncclog_list',
                link_text='Sync Logs',
                permissions=['netbox_ripe_sync.view_ripesyncclog'],
            ),
            PluginMenuItem(
                link='plugins:netbox_ripe_sync:ripeimportrun_list',
                link_text='Import Runs',
                permissions=['netbox_ripe_sync.view_ripeimportrun'],
            ),
        )),
    ),
    icon_class='mdi mdi-cloud-sync',
)
