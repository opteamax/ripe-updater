from django.conf import settings

_DEFAULTS = {
    'ripe_db': 'TEST',
    'ripe_api_key_id': None,
    'ripe_api_key_secret': None,
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


def get_config(key):
    plugin_config = settings.PLUGINS_CONFIG.get('netbox_ripe_sync', {})
    return plugin_config.get(key, _DEFAULTS.get(key))
