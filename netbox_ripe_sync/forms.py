"""Per-type structured edit forms for locally-stored RIPE objects.

Submitting a form does not change RIPE and does not change the stored object's
last-known state — it produces a *proposed* RPSL attribute list which the caller
records as a pending :class:`models.RipeChange`.  The actual push happens later,
after an explicit confirmation.
"""

from django import forms

# Maps each form field to the RPSL attribute name it edits, and whether the
# attribute is multi-valued (one value per non-empty input line).
_ROUTE_FIELDS = [
    ('description', 'descr', True),
    ('maintainer', 'mnt-by', False),
]
_DOMAIN_FIELDS = [
    ('description', 'descr', True),
    ('nameservers', 'nserver', True),
    ('admin_c', 'admin-c', False),
    ('tech_c', 'tech-c', False),
    ('zone_c', 'zone-c', False),
    ('maintainer', 'mnt-by', False),
]
_INETNUM_FIELDS = [
    ('netname', 'netname', False),
    ('description', 'descr', True),
    ('country', 'country', True),
    ('status', 'status', False),
    ('org', 'org', False),
    ('maintainer', 'mnt-by', False),
]


def merge_attributes(raw_attributes, edits):
    """Return a new RPSL attribute list applying *edits* over *raw_attributes*.

    Args:
        raw_attributes: list of {'name', 'value'} dicts (last-known RIPE state).
        edits: dict mapping attribute name -> list of replacement values.
               An empty list removes the attribute entirely.

    Edited attributes are replaced in place (at the position of their first
    occurrence); attributes not present in *edits* are preserved verbatim;
    edited attributes absent from the original are appended before ``source``.
    """
    result = []
    handled = set()
    for attr in raw_attributes:
        name = attr.get('name')
        if name in edits:
            if name not in handled:
                result.extend({'name': name, 'value': v} for v in edits[name])
                handled.add(name)
            # subsequent occurrences of an edited attr are dropped (replaced)
        else:
            result.append({'name': name, 'value': attr.get('value', '')})

    # Append any edited attribute that did not exist in the original, keeping
    # 'source' last.
    extras = [(n, vals) for n, vals in edits.items() if n not in handled and vals]
    if extras:
        source = [a for a in result if a.get('name') == 'source']
        result = [a for a in result if a.get('name') != 'source']
        for n, vals in extras:
            result.extend({'name': n, 'value': v} for v in vals)
        result.extend(source)
    return result


def diff_attributes(old, new):
    """Return a human-readable line diff between two attribute lists."""
    def fmt(attrs):
        return [f"{a.get('name')}: {a.get('value')}" for a in attrs]

    old_lines = fmt(old)
    new_lines = fmt(new)
    old_set = set(old_lines)
    new_set = set(new_lines)
    lines = []
    for line in old_lines:
        if line not in new_set:
            lines.append(f'- {line}')
    for line in new_lines:
        if line not in old_set:
            lines.append(f'+ {line}')
    return '\n'.join(lines)


class _ManagedObjectForm(forms.Form):
    """Base form that maps structured fields to/from RPSL attributes."""

    field_map = []  # list of (form_field, rpsl_name, multi)

    def __init__(self, *args, instance=None, **kwargs):
        self.instance = instance
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = (css + ' form-control').strip()
        if instance is not None and not self.is_bound:
            for form_field, _, _ in self.field_map:
                self.fields[form_field].initial = getattr(instance, form_field, '')

    def build_edits(self):
        """Return {rpsl_name: [values]} from the cleaned form data."""
        edits = {}
        for form_field, rpsl_name, multi in self.field_map:
            value = self.cleaned_data.get(form_field, '')
            if multi:
                edits[rpsl_name] = [ln.strip() for ln in value.splitlines() if ln.strip()]
            else:
                edits[rpsl_name] = [value.strip()] if value.strip() else []
        return edits

    def proposed_attributes(self):
        return merge_attributes(self.instance.raw_attributes or [], self.build_edits())


class RipeRouteForm(_ManagedObjectForm):
    field_map = _ROUTE_FIELDS
    description = forms.CharField(label='Description (descr)', required=False,
                                  widget=forms.Textarea(attrs={'rows': 2}))
    maintainer = forms.CharField(label='Maintainer (mnt-by)', required=False)


class RipeDomainForm(_ManagedObjectForm):
    field_map = _DOMAIN_FIELDS
    description = forms.CharField(label='Description (descr)', required=False,
                                  widget=forms.Textarea(attrs={'rows': 2}))
    nameservers = forms.CharField(label='Nameservers (one per line)', required=False,
                                  widget=forms.Textarea(attrs={'rows': 3}))
    admin_c = forms.CharField(label='Admin contact (admin-c)', required=False)
    tech_c = forms.CharField(label='Tech contact (tech-c)', required=False)
    zone_c = forms.CharField(label='Zone contact (zone-c)', required=False)
    maintainer = forms.CharField(label='Maintainer (mnt-by)', required=False)


class RipeInetnumForm(_ManagedObjectForm):
    field_map = _INETNUM_FIELDS
    netname = forms.CharField(label='Netname', required=False)
    description = forms.CharField(label='Description (descr)', required=False,
                                  widget=forms.Textarea(attrs={'rows': 2}))
    country = forms.CharField(label='Country (one per line)', required=False,
                              widget=forms.Textarea(attrs={'rows': 2}))
    status = forms.CharField(label='Status', required=False)
    org = forms.CharField(label='Organisation (org)', required=False)
    maintainer = forms.CharField(label='Maintainer (mnt-by)', required=False)


# Registry keyed by the URL object-kind segment.
FORM_REGISTRY = {
    'route': RipeRouteForm,
    'domain': RipeDomainForm,
    'inetnum': RipeInetnumForm,
}


def attributes_to_fields(kind, attributes):
    """Inverse of build_edits: derive structured field values from RPSL attrs.

    Used to refresh a stored object's display fields after a successful push.
    """
    from collections import defaultdict
    grouped = defaultdict(list)
    for attr in attributes:
        grouped[attr.get('name')].append(attr.get('value', ''))

    out = {}
    for form_field, rpsl_name, multi in FORM_REGISTRY[kind].field_map:
        vals = grouped.get(rpsl_name, [])
        out[form_field] = '\n'.join(vals) if multi else (vals[0] if vals else '')
    return out
