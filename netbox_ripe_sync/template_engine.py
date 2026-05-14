import json
import logging
import os

from .config import get_config
from .exceptions import TemplateNotFound
from .prefix_utils import format_cidr, is_v6

logger = logging.getLogger('netbox.plugins.ripe_sync')

TEMPLATES_FILE = 'templates.json'

# Maintainer-type attributes that get overridden in TEST mode
_MNT_ATTRS = {'mnt-by', 'mnt-ref', 'mnt-lower', 'mnt-domains', 'mnt-routes', 'mnt-irt'}
_CONTACT_ATTRS = {'admin-c', 'tech-c', 'abuse-c'}


def _load_json(path):
    if not os.path.exists(path):
        raise RuntimeError(f'Template file not found: {path}')
    with open(path) as fh:
        return json.load(fh)


class TemplateEngine:
    """Builds RIPE REST API JSON objects from file-based templates.

    Template directory layout (mirrors the original ripe-updater format):
        templates.json          — index: template-name -> {attributes, inherit}
        base_something.json     — master attributes shared across templates
        lir_org.json            — LIR slug -> RIPE org ID mapping
    """

    def __init__(self):
        self.templates_dir = get_config('templates_dir')

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def generate_object(self, prefix_str, template_name, org, country, status):
        """Return the RIPE REST API JSON body for an inetnum/inet6num object."""
        ripe_db = get_config('ripe_db')
        objecttype = 'inet6num' if is_v6(prefix_str) else 'inetnum'
        prefix_value = prefix_str if objecttype == 'inet6num' else format_cidr(prefix_str)

        local_tpl = self._read_local_template(template_name)
        master_attrs = self._read_master_template(local_tpl['inherit'])

        # Resolve org: explicit value in template > explicit in master > caller-supplied
        resolved_org = org
        for attr in local_tpl.get('attributes', []):
            if attr.get('org'):
                resolved_org = attr['org']
        for attr in master_attrs:
            if attr.get('org'):
                resolved_org = attr['org']

        # Names that the specific template defines (used to suppress master duplicates)
        template_names = {k for a in local_tpl.get('attributes', []) for k in a}

        # Template fields: non-org, non-empty
        template_fields = [
            (k, v)
            for a in local_tpl.get('attributes', [])
            for k, v in a.items()
            if v and k != 'org'
        ]

        # Master fields: non-org, non-empty.
        # Template takes precedence for any field except 'descr' and 'country',
        # which accumulate (multiple lines are valid RIPE RPSL).
        master_fields = [
            (k, v)
            for a in master_attrs
            for k, v in a.items()
            if v and k != 'org'
            and (k not in template_names or k in ('descr', 'country'))
        ]

        # Separate 'source' so it lands last (RIPE convention)
        master_source = [(k, v) for k, v in master_fields if k == 'source']
        master_rest = [(k, v) for k, v in master_fields if k != 'source']

        # Isolate descr and country for positional ordering
        tmpl_descr = [(k, v) for k, v in template_fields if k == 'descr']
        tmpl_country = [(k, v) for k, v in template_fields if k == 'country']
        tmpl_other = [(k, v) for k, v in template_fields if k not in ('descr', 'country')]

        mstr_descr = [(k, v) for k, v in master_rest if k == 'descr']
        mstr_country = [(k, v) for k, v in master_rest if k == 'country']
        mstr_other = [(k, v) for k, v in master_rest if k not in ('descr', 'country')]

        # Assemble in conventional RIPE object order:
        #   objecttype, netname, descr(s), org, country(ies),
        #   other template attrs, other master attrs, status, source
        attrs = (
            [(objecttype, prefix_value)]
            + [('netname', template_name)]
            + tmpl_descr + mstr_descr
            + [('org', resolved_org)]
            + [('country', country)]
            + tmpl_country + mstr_country
            + tmpl_other
            + mstr_other
            + [('status', status)]
            + master_source
        )

        if ripe_db == 'TEST':
            attrs = self._apply_test_overrides(attrs, objecttype)

        logger.debug(f'Generated RIPE object for {prefix_str}: {attrs}')
        return self._wrap_ripe_json(attrs, ripe_db)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _read_local_template(self, template_name):
        path = os.path.join(self.templates_dir, TEMPLATES_FILE)
        data = _load_json(path)
        tpl = data.get('templates', {}).get(template_name)
        if tpl is None:
            raise TemplateNotFound(
                f"Template '{template_name}' not found in {path}. "
                f"Available: {list(data.get('templates', {}).keys())}"
            )
        return tpl

    def _read_master_template(self, inherit_filename):
        path = os.path.join(self.templates_dir, inherit_filename)
        data = _load_json(path)
        return data.get('attributes', [])

    def _apply_test_overrides(self, attrs, objecttype):
        """Replace sensitive values with TEST-database-safe placeholders."""
        test_mnt = get_config('ripe_test_mnt')
        test_org = get_config('ripe_test_org')
        test_person = get_config('ripe_test_person')
        test_status = (
            get_config('ripe_test_status_v6')
            if objecttype == 'inet6num'
            else get_config('ripe_test_status_v4')
        )
        ripe_db = get_config('ripe_db')  # 'TEST'

        result = []
        for k, v in attrs:
            if k == 'org':
                result.append((k, test_org))
            elif k in _MNT_ATTRS:
                result.append((k, test_mnt))
            elif k in _CONTACT_ATTRS:
                result.append((k, test_person))
            elif k == 'source':
                result.append((k, ripe_db))
            elif k == 'status':
                result.append((k, test_status))
            else:
                result.append((k, v))
        return result

    @staticmethod
    def _wrap_ripe_json(attrs, ripe_db):
        return {
            'objects': {
                'object': [{
                    'source': {'id': ripe_db},
                    'attributes': {
                        'attribute': [
                            {'name': k, 'value': v}
                            for k, v in attrs
                            if v
                        ]
                    }
                }]
            }
        }
