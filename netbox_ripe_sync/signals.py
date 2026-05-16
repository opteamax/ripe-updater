import json
import logging
from pathlib import Path

from django.db.models.signals import post_delete, post_save

from .models import RipeSyncLog

logger = logging.getLogger('netbox.plugins.ripe_sync')


# ---------------------------------------------------------------------------
# Signal handlers
# ---------------------------------------------------------------------------

def _connect():
    """Connect signals. Called from PluginConfig.ready() after all apps load."""
    from ipam.models import Prefix
    post_save.connect(_prefix_saved, sender=Prefix, dispatch_uid='ripe_sync_prefix_saved')
    post_delete.connect(_prefix_deleted, sender=Prefix, dispatch_uid='ripe_sync_prefix_deleted')
    logger.debug('netbox_ripe_sync: signals connected')


def _prefix_saved(sender, instance, created, **kwargs):
    ripe_report = bool(instance.custom_field_data.get('ripe_report'))

    if ripe_report:
        action = RipeSyncLog.ACTION_CREATE if created else RipeSyncLog.ACTION_UPDATE
        _collect_and_enqueue(instance, action)
    elif not created:
        # ripe_report was turned off on an existing prefix — delete from RIPE if present
        _enqueue(str(instance.prefix), RipeSyncLog.ACTION_DELETE)


def _prefix_deleted(sender, instance, **kwargs):
    if bool(instance.custom_field_data.get('ripe_report')):
        # Snapshot all data before the ORM row disappears; no more DB calls needed
        _enqueue(str(instance.prefix), RipeSyncLog.ACTION_DELETE)


# ---------------------------------------------------------------------------
# Data collection helpers (run synchronously in the request thread)
# ---------------------------------------------------------------------------

def _collect_and_enqueue(prefix_instance, action):
    prefix_str = str(prefix_instance.prefix)
    template = _resolve_template(prefix_instance)
    country = _get_country(prefix_instance)
    org = _get_org(prefix_str)

    triggered_by = _current_username()

    if not template:
        logger.warning(
            f'ripe_template is not set for {prefix_str}; skipping RIPE sync. '
            'Set the ripe_template custom field on the prefix.'
        )
        return

    _enqueue(
        prefix_str,
        action,
        template=template,
        country=country,
        org=org,
        triggered_by=triggered_by,
    )


def _resolve_template(prefix_instance):
    """Return the template name string from the custom field, normalised to uppercase."""
    raw = prefix_instance.custom_field_data.get('ripe_template')
    if isinstance(raw, dict):
        raw = raw.get('label') or raw.get('value') or ''
    return str(raw).upper().strip() if raw else ''


def _get_country(prefix_instance):
    """Walk site -> region hierarchy to find an ISO-3166 alpha-2 country code."""
    from .config import get_config

    default = get_config('default_country')

    try:
        from iso3166 import countries_by_alpha2, countries_by_name
    except ImportError:
        logger.warning('iso3166 not installed; country lookup disabled')
        return default

    site = getattr(prefix_instance, 'site', None)
    if site is None:
        return default

    region = getattr(site, 'region', None)
    while region:
        slug_upper = region.slug.upper().replace('-', ' ')
        # Try the slug as an alpha-2 code first (e.g. 'DE', 'NL')
        if len(slug_upper) == 2 and slug_upper in countries_by_alpha2:
            return slug_upper
        # Try as a country name (e.g. 'GERMANY', 'NETHERLANDS')
        if slug_upper in countries_by_name:
            return countries_by_name[slug_upper].alpha2
        region = getattr(region, 'parent', None)

    return default


def _get_org(prefix_str):
    """Look up the RIPE org for the aggregate that contains prefix_str via lir_org.json."""
    from .config import get_config

    templates_dir = get_config('templates_dir')
    if not templates_dir:
        return None

    lir_org_file = Path(templates_dir) / 'lir_org.json'
    if not lir_org_file.exists():
        logger.debug(f'lir_org.json not found at {lir_org_file}; org will be taken from template')
        return None

    try:
        from ipam.models import Aggregate
        agg = Aggregate.objects.filter(
            prefix__net_contains_or_equals=prefix_str
        ).first()
        if agg is None:
            logger.debug(f'No aggregate found containing {prefix_str}')
            return None

        lir = agg.custom_field_data.get('lir')
        if isinstance(lir, dict):
            lir = lir.get('label') or lir.get('value') or ''
        lir = str(lir).lower().strip() if lir else ''

        if not lir:
            logger.debug(f'lir custom field is empty on aggregate for {prefix_str}')
            return None

        data = json.loads(lir_org_file.read_text(encoding='utf-8'))

        org = data.get('templates', {}).get('lir_org', {}).get(lir)
        if org is None:
            logger.warning(f"LIR '{lir}' not found in lir_org.json")
        return org

    except Exception as exc:
        logger.warning(f'org lookup failed for {prefix_str}: {exc}')
        return None


def _current_username():
    """Best-effort: return the username of the currently active request user."""
    try:
        from netbox.request_context import get_request
        req = get_request()
        if req and hasattr(req, 'user'):
            return req.user.username
    except Exception:
        pass
    return ''


# ---------------------------------------------------------------------------
# Enqueue helper
# ---------------------------------------------------------------------------

def _enqueue(prefix_str, action, template=None, country=None, org=None, triggered_by=None):
    from .jobs import run_ripe_sync

    try:
        import django_rq
        queue = django_rq.get_queue('default')
        queue.enqueue(
            run_ripe_sync,
            prefix_str=prefix_str,
            action=action,
            template=template,
            country=country,
            org=org,
            triggered_by=triggered_by,
            job_timeout=300,
        )
        logger.info(f'Enqueued RIPE sync ({action}) for {prefix_str}')
    except Exception as exc:
        logger.error(
            f'Failed to enqueue RIPE sync ({action}) for {prefix_str}: {exc}. '
            'Ensure django-rq is configured and the RQ worker is running.'
        )
