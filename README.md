# netbox-ripe-sync

A **native NetBox 4.x plugin** that automatically synchronises inetnum and inet6num
objects to the RIPE Database whenever a prefix is created, updated, or deleted in
NetBox.

> **Migration note:** This replaces the legacy `ripe-updater` Flask sidecar.
> The original code is kept in `ripeupdater/` for reference only.
> Key changes: RIPE MNT-password auth → API key auth; standalone service → native
> NetBox plugin; pynetbox webhooks → Django ORM signals.

---

## Features

- Automatic create / update / delete driven by NetBox prefix save/delete signals
- RIPE Database API key authentication (replaces deprecated MD5 password)
- IPv4 (inetnum) and IPv6 (inet6num) support
- File-based JSON template system (same format as legacy ripe-updater)
- Overlap detection and automatic resolution
- Per-prefix sync log visible in the NetBox UI
- "Sync Now" button on the prefix detail page
- Optional S3 backup of objects before modification
- Management command to create required custom fields
- REST API endpoint for programmatic sync triggers

---

## Requirements

- NetBox ≥ 4.0
- Python ≥ 3.10
- `iso3166` Python package
- RQ worker running (`python manage.py rqworker default`)
- RIPE NCC Access account with a Database API key

---

## Installation

```bash
pip install netbox-ripe-sync
# or for development:
pip install -e /path/to/netbox_ripe_sync
```

Add to NetBox's `configuration.py`:

```python
PLUGINS = ['netbox_ripe_sync']

PLUGINS_CONFIG = {
    'netbox_ripe_sync': {
        # --- Required ---
        'ripe_api_key_id':     'YOUR_KEY_ID',      # from LIR Portal → API Keys
        'ripe_api_key_secret': 'YOUR_KEY_SECRET',
        'templates_dir':       '/opt/netbox/ripe_templates',

        # --- Recommended ---
        'ripe_db':             'RIPE',   # 'TEST' (default) or 'RIPE'
        'default_country':     'DE',     # ISO 3166-1 alpha-2 fallback

        # --- Prefix size limits ---
        'smallest_prefix_v4':  31,       # prefixes larger than /31 are silently skipped
        'smallest_prefix_v6':  127,

        # --- TEST database overrides ---
        'ripe_test_mnt':       'TEST-DBM-MNT',
        'ripe_test_org':       'ORG-EIPB1-TEST',
        'ripe_test_person':    'AA1-TEST',
        'ripe_test_status_v4': 'ALLOCATED PA',
        'ripe_test_status_v6': 'ALLOCATED PA',

        # --- Optional S3 backup ---
        's3_backup_enabled':   False,
        's3_endpoint_url':     None,
        's3_access_key':       None,
        's3_secret_key':       None,
        's3_bucket':           None,
    }
}
```

Run migrations:

```bash
python manage.py migrate netbox_ripe_sync
```

Create the required custom fields:

```bash
python manage.py ripe_sync_setup
```

---

## RIPE API Key

Generate an API key in the [RIPE LIR Portal](https://my.ripe.net) under
**My Account → API Keys → Create a new Database key**.  The key is displayed
only once; save both the Key ID and the key secret.

The plugin authenticates using HTTP Basic Auth:

```http
Authorization: Basic base64(key_id:key_secret)
```

---

## Custom Fields

| Field | Model | Type | Purpose |
| --- | --- | --- | --- |
| `ripe_report` | `ipam.Prefix` | Boolean | Enable RIPE sync for this prefix |
| `ripe_template` | `ipam.Prefix` | Text | Template key from `templates.json` |
| `lir` | `ipam.Aggregate` | Text | LIR slug, maps to RIPE org via `lir_org.json` |

---

## Template Files

Place all template files in `templates_dir`:

```text
templates_dir/
├── templates.json          ← index of templates
├── lir_org.json            ← LIR slug → RIPE org ID
├── base_mycompany.json     ← base attributes (admin-c, mnt-by, source, …)
└── base_mycustomer1.json   ← alternate base for different abuse-c etc.
```

Formats are identical to the legacy ripe-updater — copy your existing files
unchanged.

---

## Region → Country Mapping

The plugin walks a prefix's Site → Region hierarchy looking for an ISO 3166-1
alpha-2 country code.  Either:

- Name a region with a two-letter slug (`de`, `nl`, `us`) — matched as alpha-2, or
- Name a region after a full country name (`germany`, `netherlands`) — matched
  against `iso3166.countries_by_name`.

If no match is found, `default_country` is used.

---

## Known Limitations

- A prefix and its child prefixes cannot both have `ripe_report = True` — RIPE
  only allows one level below an aggregate. Workaround: disable `ripe_report`
  on either the parent or the children.
- Widening a prefix (e.g. `/27` → `/26`) requires disabling `ripe_report`,
  resizing, then re-enabling — the same limitation as the legacy tool.
