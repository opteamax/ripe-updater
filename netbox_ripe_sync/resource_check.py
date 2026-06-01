"""Counter-check that a prefix belongs to resources we actually hold.

Before any object is written to the RIPE Database, the prefix it describes is
verified to be contained within a RIPE LIR Portal *My Resources* allocation or
assignment. This guards against accidentally creating/modifying RIPE objects for
address space that is not ours.

The My Resources network list is fetched via :class:`MyResourcesClient` and
cached (NetBox's Django cache) for ``my_resources_cache_ttl`` seconds, so the
check does not hit the LIR Portal API on every push.
"""

import logging
from ipaddress import ip_network

from django.core.cache import cache

from .config import get_config
from .exceptions import ResourceMembershipError
from .my_resources_client import MyResourcesClient

logger = logging.getLogger('netbox.plugins.ripe_sync')

_CACHE_KEY = 'netbox_ripe_sync:my_resource_networks'

# Resource categories that count as "ours" for containment purposes. A prefix
# inside one of our allocations (or assignments, or legacy/ERX blocks) is ours.
_RESOURCE_KEYS = (
    'ipv4_allocations',
    'ipv4_assignments',
    'ipv4_legacy',
    'ipv6_allocations',
    'ipv6_assignments',
)


def get_my_resource_networks(force_refresh: bool = False) -> list[str]:
    """Return the list of CIDR strings we hold per the My Resources API (cached)."""
    if not force_refresh:
        cached = cache.get(_CACHE_KEY)
        if cached is not None:
            return cached

    client = MyResourcesClient()  # raises MissingConfig if lir_portal_api_key unset
    data = client.get_all()

    networks: list[str] = []
    for key in _RESOURCE_KEYS:
        for item in data.get(key, []):
            raw = item.get('prefix')
            if not raw:
                continue
            try:
                networks.append(str(ip_network(raw, strict=False)))
            except ValueError:
                logger.debug(f'My Resources: skipping unparseable prefix {raw!r}')

    if networks:
        ttl = int(get_config('my_resources_cache_ttl') or 3600)
        cache.set(_CACHE_KEY, networks, ttl)
    else:
        # Don't cache an empty result — likely a transient API hiccup; retry next time.
        logger.warning('My Resources returned no networks; membership check has nothing to match')
    return networks


def prefix_within_my_resources(prefix_str: str) -> tuple[bool, str | None]:
    """Return (is_member, containing_network) for *prefix_str* against My Resources."""
    try:
        net = ip_network(prefix_str, strict=False)
    except ValueError:
        return False, None

    for raw in get_my_resource_networks():
        parent = ip_network(raw, strict=False)
        if parent.version == net.version and net.subnet_of(parent):
            return True, str(parent)
    return False, None


def assert_within_my_resources(prefix_str: str) -> None:
    """Raise :class:`ResourceMembershipError` if *prefix_str* is not ours.

    When ``require_my_resources_membership`` is False, a non-member only logs a
    warning. If the My Resources list cannot be fetched (no API key / API error)
    the underlying exception propagates — i.e. the check fails closed when
    enforcement is enabled.
    """
    enforce = bool(get_config('require_my_resources_membership'))

    if not enforce:
        try:
            ok, parent = prefix_within_my_resources(prefix_str)
        except Exception as exc:  # noqa: BLE001 - advisory only when not enforcing
            logger.warning(f'My Resources membership check unavailable for {prefix_str}: {exc}')
            return
        if not ok:
            logger.warning(
                f'{prefix_str} is NOT within any My Resources allocation/assignment '
                '(membership enforcement disabled — proceeding)'
            )
        return

    ok, parent = prefix_within_my_resources(prefix_str)
    if not ok:
        raise ResourceMembershipError(
            f'{prefix_str} is not within any RIPE My Resources allocation or '
            'assignment; refusing to write it to the RIPE Database. Re-run the '
            'My Resources import if your resources changed, or set '
            'require_my_resources_membership=False to override.'
        )
    logger.info(f'My Resources membership OK: {prefix_str} ⊆ {parent}')
