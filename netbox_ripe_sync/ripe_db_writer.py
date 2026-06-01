"""Generic writer for arbitrary RIPE Database objects.

Where :class:`ripe_client.RipeClient` is purpose-built for template-driven
inetnum/inet6num sync, this writer pushes any object type (inetnum, inet6num,
route, route6, domain) given a plain list of RPSL attributes.  It is the engine
behind the confirmed-push step of the local-edit workflow.
"""

import logging
from urllib.parse import quote

import requests

from .auth import write_authorization
from .config import get_config
from .exceptions import MissingConfig, RipeAPIError
from .prefix_utils import format_cidr

logger = logging.getLogger('netbox.plugins.ripe_sync')

_DB_BASES = {
    'RIPE': 'https://rest.db.ripe.net/ripe',
    'TEST': 'https://rest-test.db.ripe.net/test',
}


class RipeDbWriter:
    """POST / PUT / DELETE for arbitrary RIPE objects via the REST API."""

    def __init__(self) -> None:
        self.ripe_db = get_config('ripe_db')
        if self.ripe_db not in _DB_BASES:
            raise MissingConfig(f"ripe_db must be 'RIPE' or 'TEST', got '{self.ripe_db}'")
        self.base_url = _DB_BASES[self.ripe_db]

    # ------------------------------------------------------------------
    # Public operations
    # ------------------------------------------------------------------

    def create(self, object_type, attributes):
        """POST a new object. Returns the RIPE response text."""
        url = f'{self.base_url}/{object_type}'
        resp = requests.post(url, json=self._wrap(attributes), headers=self._auth_headers())
        return self._handle(resp, f'POST {object_type}')

    def modify(self, object_type, primary_key, attributes):
        """PUT (replace) an existing object. Returns the RIPE response text."""
        url = f'{self.base_url}/{object_type}/{self._encode_key(object_type, primary_key)}'
        resp = requests.put(url, json=self._wrap(attributes), headers=self._auth_headers())
        return self._handle(resp, f'PUT {object_type} {primary_key}')

    def delete(self, object_type, primary_key):
        """DELETE an object. Returns the RIPE response text (404 is tolerated)."""
        url = f'{self.base_url}/{object_type}/{self._encode_key(object_type, primary_key)}'
        resp = requests.delete(url, headers=self._auth_headers())
        if resp.status_code == 404:
            return f'{object_type} {primary_key} already absent (404)'
        return self._handle(resp, f'DELETE {object_type} {primary_key}')

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _handle(self, resp, label):
        if resp.ok:
            logger.info(f'{label} succeeded ({self.ripe_db})')
            return resp.text
        errors = self._extract_errors(resp)
        raise RipeAPIError(f'{label} failed: {errors}')

    # RIPE generates these itself; sending them on create/modify is rejected.
    _SERVER_MANAGED = {'created', 'last-modified'}

    def _wrap(self, attributes):
        """Build the RIPE REST body from a [{'name','value'}, ...] attribute list.

        Drops server-managed attributes (created/last-modified) and ensures a
        'source' attribute matching the configured database is present.
        """
        attrs = [
            a for a in attributes
            if a.get('value') not in (None, '')
            and a.get('name', '').lower() not in self._SERVER_MANAGED
        ]
        if not any(a.get('name') == 'source' for a in attrs):
            attrs.append({'name': 'source', 'value': self.ripe_db})
        return {
            'objects': {
                'object': [{
                    'source': {'id': self.ripe_db},
                    'attributes': {'attribute': attrs},
                }]
            }
        }

    @staticmethod
    def _encode_key(object_type, primary_key):
        """URL-encode the primary key for the object path.

        IPv4 inetnum keys are RIPE ranges ('a - b'); a CIDR is converted first.
        """
        key = primary_key
        if object_type == 'inetnum' and '-' not in key and '/' in key:
            key = format_cidr(key)
        return quote(key, safe='')

    def _auth_headers(self):
        return {
            'Authorization': write_authorization(),
            'Content-Type': 'application/json',
            'Accept': 'application/json; charset=utf-8',
        }

    @staticmethod
    def _extract_errors(resp):
        try:
            msgs = resp.json().get('errormessages', {}).get('errormessage', [])
            return '; '.join(m.get('text', '') for m in msgs) or resp.text
        except Exception:
            return resp.text
