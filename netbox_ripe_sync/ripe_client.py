import json
import logging
from ipaddress import ip_address, ip_network, summarize_address_range

import requests

from .backup import BackupManager
from .config import get_config
from .exceptions import MissingConfig, OverlapConflict, RipeAPIError
from .prefix_utils import find, format_cidr, format_ripe_object, is_v6, validate_prefix
from .template_engine import TemplateEngine

logger = logging.getLogger('netbox.plugins.ripe_sync')

_DB_BASES = {
    'RIPE': 'https://rest.db.ripe.net/ripe',
    'TEST': 'https://rest-test.db.ripe.net/test',
}
_SEARCH_BASES = {
    'RIPE': 'https://rest.db.ripe.net/search',
    'TEST': 'https://rest-test.db.ripe.net/search',
}

_DEFAULT_STATUS = {
    'inet6num': 'ASSIGNED',
    'inetnum': 'ASSIGNED PA',
}


class RipeClient:
    """Manages create / update / delete of a single inetnum or inet6num object."""

    def __init__(self, prefix_str, template, country, org):
        self.prefix = prefix_str
        self.template = template
        self.country = country
        self.org = org

        validate_prefix(prefix_str)

        self.ripe_db = get_config('ripe_db')
        if self.ripe_db not in _DB_BASES:
            raise MissingConfig(f"ripe_db must be 'RIPE' or 'TEST', got '{self.ripe_db}'")

        self.objecttype = 'inet6num' if is_v6(prefix_str) else 'inetnum'
        self.status = _DEFAULT_STATUS[self.objecttype]
        self.base_url = _DB_BASES[self.ripe_db]
        self.object_url = f'{self.base_url}/{self.objecttype}'
        self.search_url = _SEARCH_BASES[self.ripe_db]

        self._engine = TemplateEngine()
        self._backup = BackupManager()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def push(self):
        """Create or update the RIPE object for this prefix. Returns a status message."""
        if not self.template:
            raise RipeAPIError(
                f'No RIPE template configured for {self.prefix}. '
                'Set the ripe_template custom field on the prefix.'
            )

        self._save_backup()
        existing = self._get_existing()
        new_obj = self._engine.generate_object(
            self.prefix, self.template, self.org, self.country, self.status
        )

        if existing:
            return self._put(existing, new_obj)
        return self._post(new_obj)

    def delete(self):
        """Delete the RIPE object for this prefix. Returns a status message."""
        self._save_backup()
        key = self.prefix if self.objecttype == 'inet6num' else format_cidr(self.prefix)
        url = f'{self.object_url}/{key}'

        resp = requests.delete(url, headers=self._auth_headers())
        if resp.status_code == 404:
            return f'{self.prefix} not found in RIPE DB (already absent)'
        if not resp.ok:
            errors = self._extract_errors(resp)
            raise RipeAPIError(f'DELETE {self.prefix} failed: {errors}')

        logger.info(f'Deleted {self.prefix} from RIPE DB ({self.ripe_db})')
        return f'Deleted {self.prefix} from RIPE DB'

    # ------------------------------------------------------------------
    # Internal HTTP helpers
    # ------------------------------------------------------------------

    def _auth_headers(self):
        from .auth import write_authorization
        return {
            'Authorization': write_authorization(),
            'Content-Type': 'application/json',
            'Accept': 'application/json; charset=utf-8',
        }

    def _read_headers(self):
        return {'Accept': 'application/json; charset=utf-8'}

    def _get_existing(self):
        """Fetch the current RIPE object for this prefix. Returns JSON dict or None."""
        key = self.prefix if self.objecttype == 'inet6num' else format_cidr(self.prefix)
        resp = requests.get(
            f'{self.object_url}/{key}?unfiltered',
            headers=self._read_headers(),
        )
        if resp.ok:
            return resp.json()
        if resp.status_code == 404:
            return None
        resp.raise_for_status()

    def _post(self, new_obj):
        resp = requests.post(self.object_url, json=new_obj, headers=self._auth_headers())
        if resp.ok:
            logger.info(f'Created {self.prefix} in RIPE DB ({self.ripe_db})')
            return f'Created {self.prefix} in RIPE DB'

        # On 400, check whether an overlapping prefix is blocking creation
        if resp.status_code == 400:
            overlap = self._find_overlap()
            if overlap and self._can_delete_overlap(overlap):
                self._delete_overlap(overlap)
                retry = requests.post(self.object_url, json=new_obj, headers=self._auth_headers())
                if retry.ok:
                    logger.info(
                        f'Created {self.prefix} in RIPE DB after removing overlap {overlap}'
                    )
                    return f'Created {self.prefix} (removed overlapping {overlap})'
                errors = self._extract_errors(retry)
                raise RipeAPIError(f'POST {self.prefix} failed after overlap removal: {errors}')
            elif overlap:
                raise OverlapConflict(
                    f'Overlapping prefix {overlap} exists in both RIPE DB and NetBox — '
                    'manual resolution required'
                )

        errors = self._extract_errors(resp)
        raise RipeAPIError(f'POST {self.prefix} failed: {errors}')

    def _put(self, old_obj, new_obj):
        key = self.prefix if self.objecttype == 'inet6num' else format_cidr(self.prefix)
        resp = requests.put(
            f'{self.object_url}/{key}',
            json=new_obj,
            headers=self._auth_headers(),
        )
        if not resp.ok:
            errors = self._extract_errors(resp)
            raise RipeAPIError(f'PUT {self.prefix} failed: {errors}')

        logger.info(f'Updated {self.prefix} in RIPE DB ({self.ripe_db})')
        return f'Updated {self.prefix} in RIPE DB'

    # ------------------------------------------------------------------
    # Overlap handling (mirrors original logic)
    # ------------------------------------------------------------------

    def _find_overlap(self):
        """Return the string CIDR of an overlapping prefix in RIPE, or None."""
        params = {
            'source': self.ripe_db,
            'type-filter': self.objecttype,
            'flags': 'no-referenced',
            'query-string': self.prefix,
        }
        resp = requests.get(self.search_url, params=params, headers=self._read_headers())

        if resp.status_code == 404:
            return None
        if not resp.ok:
            logger.warning(f'Overlap search failed for {self.prefix}: {resp.status_code}')
            return None

        try:
            objects = resp.json()['objects']['object']
            pk_value = objects[0]['primary-key']['attribute'][0]['value']
        except (KeyError, IndexError):
            return None

        # Parse the primary key back to an ip_network
        try:
            if self.objecttype == 'inet6num':
                overlap_net = ip_network(pk_value, strict=False)
            else:
                start, end = (s.strip() for s in pk_value.split('-'))
                overlap_net = next(summarize_address_range(ip_address(start), ip_address(end)))
        except (ValueError, StopIteration):
            logger.warning(f'Could not parse overlap key: {pk_value!r}')
            return None

        # Suppress if it turns out to be the same prefix (no real overlap)
        if overlap_net == ip_network(self.prefix, strict=False):
            return None

        return str(overlap_net)

    def _can_delete_overlap(self, overlap_str):
        """Return True only if the overlap is absent from NetBox (safe to remove)."""
        try:
            from ipam.models import Aggregate, Prefix
            return not (
                Prefix.objects.filter(prefix=overlap_str).exists()
                or Aggregate.objects.filter(prefix=overlap_str).exists()
            )
        except Exception as exc:
            logger.warning(f'NetBox overlap check failed for {overlap_str}: {exc}')
            return False

    def _delete_overlap(self, overlap_str):
        key = overlap_str if is_v6(overlap_str) else format_cidr(overlap_str)
        resp = requests.delete(
            f'{self.object_url}/{key}',
            headers=self._auth_headers(),
        )
        if resp.status_code not in (200, 404):
            errors = self._extract_errors(resp)
            raise RipeAPIError(f'Could not delete overlapping prefix {overlap_str}: {errors}')
        logger.info(f'Deleted overlapping prefix {overlap_str} from RIPE DB')

    # ------------------------------------------------------------------
    # Backup
    # ------------------------------------------------------------------

    def _save_backup(self):
        existing = self._get_existing()
        if existing:
            filename = f"prefix_{self.prefix.replace('/', '_')}.json"
            self._backup.put(filename, json.dumps(existing))

    # ------------------------------------------------------------------
    # Error parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_errors(resp):
        try:
            msgs = resp.json().get('errormessages', {}).get('errormessage', [])
            return '; '.join(m.get('text', '') for m in msgs) or resp.text
        except Exception:
            return resp.text
