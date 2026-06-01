from netbox.plugins import PluginConfig


class NetboxRipeSyncConfig(PluginConfig):
    name = 'netbox_ripe_sync'
    verbose_name = 'NetBox RIPE Sync'
    description = 'Synchronises inetnum/inet6num objects to the RIPE Database via API key auth'
    version = '1.0.0'
    author = 'NetBox RIPE Sync'
    author_email = ''
    base_url = 'ripe-sync'
    min_version = '4.0.0'

    default_settings = {
        # RIPE Database REST API (inetnum/inet6num sync)
        'ripe_db': 'TEST',
        'ripe_api_key_id': None,
        'ripe_api_key_secret': None,
        'ripe_whois_api_token': None,
        # LIR Portal My Resources API (resource import)
        'lir_portal_api_key': None,
        # RIPE Database inverse-lookup import
        'ripe_db_maintainers': [],
        'ripe_db_orgs': [],
        'templates_dir': '/opt/netbox/ripe_templates',
        'smallest_prefix_v4': 31,
        'smallest_prefix_v6': 127,
        's3_backup_enabled': False,
        's3_endpoint_url': None,
        's3_access_key': None,
        's3_secret_key': None,
        's3_bucket': None,
        'default_country': None,
        'ripe_test_mnt': 'TEST-DBM-MNT',
        'ripe_test_org': 'ORG-EIPB1-TEST',
        'ripe_test_person': 'AA1-TEST',
        'ripe_test_status_v4': 'ALLOCATED PA',
        'ripe_test_status_v6': 'ALLOCATED PA',
    }

    def ready(self):
        from .signals import _connect
        _connect()
        super().ready()


config = NetboxRipeSyncConfig
