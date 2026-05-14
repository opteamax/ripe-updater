from ipaddress import ip_network

from .config import get_config
from .exceptions import NotRoutablePrefix, PrefixTooSmall


def is_v6(prefix_str):
    return ip_network(prefix_str, strict=False).version == 6


def format_cidr(prefix_str):
    """Convert CIDR notation to RIPE range notation for IPv4.

    '192.0.2.0/24'  ->  '192.0.2.0 - 192.0.2.255'
    """
    net = ip_network(prefix_str, strict=False)
    return f'{net.network_address} - {net.broadcast_address}'


def validate_prefix(prefix_str):
    net = ip_network(prefix_str, strict=False)

    if is_v6(prefix_str):
        max_len = int(get_config('smallest_prefix_v6'))
        if net.prefixlen > max_len:
            raise PrefixTooSmall(
                f'IPv6 prefix /{net.prefixlen} exceeds configured minimum /{max_len}'
            )
        if not net.is_global or net.is_loopback or net.is_reserved or net.is_multicast or net.is_link_local:
            raise NotRoutablePrefix(f'{prefix_str} is not a globally routable IPv6 prefix')
    else:
        max_len = int(get_config('smallest_prefix_v4'))
        if net.prefixlen > max_len:
            raise PrefixTooSmall(
                f'IPv4 prefix /{net.prefixlen} exceeds configured minimum /{max_len}'
            )
        if net.is_loopback or net.is_reserved or net.is_private or net.is_multicast:
            raise NotRoutablePrefix(f'{prefix_str} is not a globally routable IPv4 prefix')


def find(path, obj):
    """Navigate a nested dict using a dotted path string.

    find('objects.object', {'objects': {'object': [1, 2]}}) -> [1, 2]
    """
    for key in path.split('.'):
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def flatten_ripe_attributes(ripe_object):
    """Return [(name, value), ...] from a single RIPE REST API object dict."""
    attrs = find('attributes.attribute', ripe_object) or []
    return [(a.get('name', ''), a.get('value', '')) for a in attrs]


def format_ripe_object(ripe_object, line_prefix=''):
    """Return a human-readable text representation of a RIPE object."""
    if not ripe_object:
        return ''
    return '\n'.join(
        f'{line_prefix}{name}:\t{value}'
        for name, value in flatten_ripe_attributes(ripe_object)
    )
