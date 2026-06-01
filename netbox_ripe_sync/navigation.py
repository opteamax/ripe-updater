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
            PluginMenuItem(
                link='plugins:netbox_ripe_sync:ripeinetnumobject_list',
                link_text='Inetnum Objects',
                permissions=['netbox_ripe_sync.view_ripeinetnumobject'],
            ),
            PluginMenuItem(
                link='plugins:netbox_ripe_sync:riperouteobject_list',
                link_text='Route Objects',
                permissions=['netbox_ripe_sync.view_riperouteobject'],
            ),
            PluginMenuItem(
                link='plugins:netbox_ripe_sync:ripedomainobject_list',
                link_text='Domain Objects',
                permissions=['netbox_ripe_sync.view_ripedomainobject'],
            ),
            PluginMenuItem(
                link='plugins:netbox_ripe_sync:ripechange_list',
                link_text='Pending Changes',
                permissions=['netbox_ripe_sync.view_ripechange'],
            ),
        )),
    ),
    icon_class='mdi mdi-cloud-sync',
)
