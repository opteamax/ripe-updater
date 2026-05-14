"""Client for the RIPE NCC LIR Portal "My Resources" API.

Authentication uses a separate API key from the RIPE Database key.
Generate one in the LIR Portal under Tools → API Access Keys.
Pass it via header:  ncc-api-authorization: <api-key>

Base URL: https://lirportal.ripe.net/myresources/v1/resources
"""

import logging

import requests

from .config import get_config
from .exceptions import MissingConfig, RipeSyncException

logger = logging.getLogger('netbox.plugins.ripe_sync')

_BASE_URL = 'https://lirportal.ripe.net/myresources/v1/resources'


class MyResourcesError(RipeSyncException):
    pass


class MyResourcesClient:
    """Fetches all resource types from the RIPE LIR Portal My Resources API."""

    def __init__(self):
        self.api_key = get_config('lir_portal_api_key')
        if not self.api_key:
            raise MissingConfig(
                'lir_portal_api_key must be set in PLUGINS_CONFIG to use the '
                'My Resources import feature. Generate a key in the LIR Portal '
                'under Tools → API Access Keys.'
            )

    # ------------------------------------------------------------------
    # Public resource fetchers
    # ------------------------------------------------------------------

    def get_asns(self):
        """Return list of ASN dicts: [{asn, registrationDate, status, ...}, ...]"""
        data = self._get('/asn')
        # API may return 'asns' or 'asnAllocations' depending on version
        return data.get('asns') or data.get('asnAllocations') or []

    def get_ipv4_allocations(self):
        data = self._get('/ipv4/allocations')
        return data.get('ipv4Allocations') or []

    def get_ipv4_assignments(self):
        data = self._get('/ipv4/assignments')
        return data.get('ipv4Assignments') or []

    def get_ipv4_legacy(self):
        data = self._get('/ipv4/erxresources')
        return data.get('ipv4ErxResources') or data.get('erxResources') or []

    def get_ipv6_allocations(self):
        data = self._get('/ipv6/allocations')
        return data.get('ipv6Allocations') or []

    def get_ipv6_assignments(self):
        data = self._get('/ipv6/assignments')
        return data.get('ipv6Assignments') or []

    def get_all(self):
        """Fetch every resource type in one call.

        Returns a dict keyed by resource category.  Any endpoint that returns
        an empty list or errors is represented as an empty list so callers
        don't need to guard for missing keys.
        """
        results = {}
        fetchers = {
            'asns': self.get_asns,
            'ipv4_allocations': self.get_ipv4_allocations,
            'ipv4_assignments': self.get_ipv4_assignments,
            'ipv4_legacy': self.get_ipv4_legacy,
            'ipv6_allocations': self.get_ipv6_allocations,
            'ipv6_assignments': self.get_ipv6_assignments,
        }
        for key, fetcher in fetchers.items():
            try:
                results[key] = fetcher()
                logger.debug(f'My Resources: fetched {len(results[key])} {key}')
            except MyResourcesError as exc:
                logger.warning(f'My Resources: skipping {key} — {exc}')
                results[key] = []
        return results

    # ------------------------------------------------------------------
    # HTTP helper
    # ------------------------------------------------------------------

    def _get(self, path):
        url = f'{_BASE_URL}{path}?format=JSON'
        logger.debug(f'My Resources GET {url}')
        try:
            resp = requests.get(
                url,
                headers={'ncc-api-authorization': self.api_key},
                timeout=30,
            )
        except requests.RequestException as exc:
            raise MyResourcesError(f'Network error fetching {url}: {exc}') from exc

        if resp.status_code == 401:
            raise MyResourcesError(
                'Unauthorized — check lir_portal_api_key in PLUGINS_CONFIG'
            )
        if resp.status_code == 404:
            # Endpoint not applicable for this LIR (e.g. no ERX resources)
            logger.info(f'My Resources: {path} returned 404 (no resources of this type)')
            return {}
        if not resp.ok:
            raise MyResourcesError(
                f'My Resources API error {resp.status_code} for {path}: {resp.text[:200]}'
            )

        try:
            return resp.json()
        except ValueError as exc:
            raise MyResourcesError(f'Invalid JSON from {url}: {exc}') from exc

    # ------------------------------------------------------------------
    # Static helpers (data normalisation)
    # ------------------------------------------------------------------

    @staticmethod
    def parse_asn_number(raw):
        """Return an integer ASN from 'AS12345' or 12345 or '12345'."""
        if raw is None:
            return None
        s = str(raw).strip().upper().lstrip('AS').strip()
        try:
            return int(s)
        except ValueError:
            return None
