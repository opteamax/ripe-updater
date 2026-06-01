"""Client for discovering objects in the RIPE Database via inverse lookups.

Unlike the LIR Portal My Resources API (see ``my_resources_client.py``), this
queries the RIPE Database REST *search* API directly.  Given a maintainer
(``mnt-by``) name or an organisation (``org``) id, an inverse lookup returns
every ``inetnum`` / ``inet6num`` / ``route`` / ``route6`` object that references
it — i.e. every resource you maintain, including assignments and route objects
that the My Resources API does not expose.

No authentication is required for read access.  The ``source`` (RIPE / TEST) is
taken from the ``ripe_db`` plugin setting so the search hits the same database
the outbound sync writes to.
"""

import logging

import requests

from .config import get_config
from .exceptions import MissingConfig, RipeSyncException
from .prefix_utils import find, flatten_ripe_attributes

logger = logging.getLogger('netbox.plugins.ripe_sync')

# Mirrors RipeClient._SEARCH_BASES — kept local to avoid a hard import cycle.
_SEARCH_BASES = {
    'RIPE': 'https://rest.db.ripe.net/search',
    'TEST': 'https://rest-test.db.ripe.net/search',
}

# Object types we know how to import, in the order callers expect them.
OBJECT_TYPES = ('inetnum', 'inet6num', 'route', 'route6', 'domain')


class RipeDbSearchError(RipeSyncException):
    pass


class RipeDbSearchClient:
    """Fetches a LIR's objects from the RIPE Database via inverse lookups."""

    def __init__(self) -> None:
        self.source = get_config('ripe_db')
        if self.source not in _SEARCH_BASES:
            raise MissingConfig(f"ripe_db must be 'RIPE' or 'TEST', got '{self.source}'")
        self.search_url = _SEARCH_BASES[self.source]
        self.maintainers = list(get_config('ripe_db_maintainers') or [])
        self.orgs = list(get_config('ripe_db_orgs') or [])

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def get_all(self, object_types=None) -> dict[str, list[dict]]:
        """Return a dict keyed by object type, deduplicated across lookups.

        Each value is a list of parsed object dicts (see ``_parse_object``).
        ``object_types`` restricts both the API query and the returned keys;
        ``None`` means all of :data:`OBJECT_TYPES`.
        """
        types = tuple(object_types) if object_types else OBJECT_TYPES

        if not self.maintainers and not self.orgs:
            raise MissingConfig(
                'No RIPE Database lookup targets configured. Set ripe_db_maintainers '
                'and/or ripe_db_orgs in PLUGINS_CONFIG to import from the RIPE Database.'
            )

        results: dict[str, list[dict]] = {t: [] for t in types}
        seen: set[tuple[str, str]] = set()

        lookups = (
            [('mnt-by', mnt) for mnt in self.maintainers]
            + [('org', org) for org in self.orgs]
        )
        for inverse_attr, value in lookups:
            for obj in self._inverse_lookup(inverse_attr, value, types):
                key = (obj['type'], obj['primary_key'])
                if key in seen:
                    continue
                seen.add(key)
                results.setdefault(obj['type'], []).append(obj)

        for t in types:
            logger.info(f'RIPE DB import: {len(results.get(t, []))} {t} object(s) discovered')
        return results

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _inverse_lookup(self, inverse_attr: str, value: str, types) -> list[dict]:
        """Run one inverse-lookup search and return parsed objects."""
        params = [
            ('source', self.source),
            ('query-string', value),
            ('inverse-attribute', inverse_attr),
            # no-referenced: return only the matching objects, not the
            # person/role/mntner objects they reference.
            ('flags', 'no-referenced'),
        ]
        params += [('type-filter', t) for t in types]

        logger.debug(f'RIPE DB inverse lookup {inverse_attr}={value} on {self.source}')
        try:
            resp = requests.get(self.search_url, params=params,
                                headers={'Accept': 'application/json'}, timeout=60)
        except requests.RequestException as exc:
            raise RipeDbSearchError(
                f'Network error during inverse lookup {inverse_attr}={value}: {exc}'
            ) from exc

        if resp.status_code == 404:
            # No objects reference this maintainer/org.
            logger.info(f'RIPE DB: {inverse_attr}={value} matched no objects (404)')
            return []
        if not resp.ok:
            raise RipeDbSearchError(
                f'RIPE DB search error {resp.status_code} for {inverse_attr}={value}: '
                f'{resp.text[:200]}'
            )

        try:
            data = resp.json()
        except ValueError as exc:
            raise RipeDbSearchError(
                f'Invalid JSON from RIPE DB search for {inverse_attr}={value}: {exc}'
            ) from exc

        objects = find('objects.object', data) or []
        return [self._parse_object(o) for o in objects]

    @staticmethod
    def _parse_object(raw: dict) -> dict:
        """Normalise one RIPE REST object into a flat, easy-to-consume dict."""
        attrs = flatten_ripe_attributes(raw)  # [(name, value), ...]
        pk_attrs = find('primary-key.attribute', raw) or []
        primary_key = ' '.join(a.get('value', '') for a in pk_attrs)
        return {
            'type': raw.get('type', ''),
            'primary_key': primary_key,
            'attributes': attrs,
        }
