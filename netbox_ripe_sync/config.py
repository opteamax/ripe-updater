from typing import Any

from django.conf import settings

_DEFAULTS: dict[str, Any] = {
    # RIPE Database REST API (inetnum/inet6num sync)
    'ripe_db': 'TEST',
    'ripe_api_key_id': None,
    'ripe_api_key_secret': None,
    # RIPE Database API key for *write* operations (create/modify/delete).
    # Generated at https://apps.db.ripe.net/db-web-ui/api-keys and linked to the
    # maintainer via auth: SSO. Accepts 'keyId:password', a base64 blob, or the
    # full 'Basic <base64>' header value.
    'ripe_whois_api_token': None,
    # LIR Portal My Resources API (resource import)
    'lir_portal_api_key': None,
    # RIPE Database inverse-lookup import (inetnum/inet6num/route/route6)
    # Lists of maintainer (mnt-by) names and/or organisation (org) ids whose
    # objects should be discovered and imported from the RIPE Database.
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


def get_config(key: str) -> Any:
    plugin_config = settings.PLUGINS_CONFIG.get('netbox_ripe_sync', {})
    return plugin_config.get(key, _DEFAULTS.get(key))
