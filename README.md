# netbox-ripe-sync

A **native NetBox 4.x plugin** that:

1. **Automatically synchronises** inetnum and inet6num objects to the RIPE
   Database whenever a prefix is created, updated, or deleted in NetBox.
2. **Imports resources** from the RIPE LIR Portal My Resources API — pulling
   your ASNs, allocations, and assignments directly into NetBox.
3. **Imports objects from the RIPE Database** by inverse lookup — inetnum,
   inet6num, route, route6 and reverse-DNS domain objects you maintain.
4. **Edits imported objects locally** and pushes the changes back to the RIPE
   Database, gated behind an explicit confirmation.

---

## Features

### RIPE Database Sync (outbound)

- Automatic create / update / delete driven by NetBox prefix save/delete signals
- RIPE Database API key authentication (replaces deprecated MD5 password)
- IPv4 (`inetnum`) and IPv6 (`inet6num`) support
- File-based JSON template system (same format as legacy ripe-updater)
- Overlap detection and automatic resolution
- Per-prefix sync log visible in the NetBox UI
- "Sync Now" button on the prefix detail page
- Optional S3 backup of RIPE objects before modification

### My Resources Import (inbound)

- Fetch all resources from the RIPE LIR Portal My Resources API in one click
- Imports ASNs → `ipam.ASN`, allocations → `ipam.Aggregate`, assignments → `ipam.Prefix`
- Dry-run mode — preview what would be created without touching NetBox
- Selective import via resource-type filter
- Never overwrites existing objects (idempotent)
- All imported objects tagged `ripe-my-resources` for easy identification
- Import run history with per-type counters and per-resource error detail
- Background execution via django-rq so large imports don't block the UI
- Management command (`ripe_import_resources`) for CLI / cron use without a worker

### RIPE Database Import (inbound)

- Discovers **every object you maintain** in the RIPE Database via inverse lookup
  on configurable maintainers (`mnt-by`) and/or organisations (`org`)
- Imports `inetnum` / `inet6num` → `ipam.Aggregate` (ALLOCATED\*) or `ipam.Prefix`
  (other statuses); **missing IP ranges are created** in NetBox
- Imports `route` / `route6` objects into a dedicated `RipeRouteObject` model
  (prefix + origin AS), linked to the matching NetBox Prefix when one exists
- Imports reverse-DNS `domain` objects into a dedicated `RipeDomainObject` model
- Keeps an editable RPSL mirror of every imported object (re-import refreshes it)
- Same dry-run, selective-type, idempotent, background-job and run-history support
  as the My Resources import; created objects tagged `ripe-database`
- Management command (`ripe_import_db`) for CLI / cron use without a worker

### Local editing & confirmed push (outbound)

- Edit any imported RIPE object (inetnum/inet6num, route/route6, domain) via a
  structured per-type form in the NetBox UI
- Edits are **stored locally** as pending changes — nothing is sent to RIPE on save
- A **Pending Changes** queue shows every proposed create/modify/delete with a diff
- Pushing to the RIPE Database requires an **explicit, separate confirmation** and
  is recorded with who/when, the RIPE response, and success/failure state

---

## Requirements

- NetBox ≥ 4.0
- Python ≥ 3.10
- `iso3166` Python package
- RQ worker running (`python manage.py rqworker default`)
- RIPE NCC Access account with:
  - A **Database API key** (`ripe_whois_api_token`) for writing to the RIPE
    Database (outbound sync and confirmed pushes), linked to your maintainer
    via an `auth: SSO` attribute
  - An **LIR Portal API key** (for My Resources import)
  - (Reading / importing from the RIPE Database needs no key)

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
        # --- RIPE Database sync (outbound) ---
        'ripe_api_key_id':     'YOUR_KEY_ID',      # LIR Portal → API Keys → Database key
        'ripe_api_key_secret': 'YOUR_KEY_SECRET',
        # Required to WRITE to the RIPE Database (create/modify/delete). Generate a
        # Database API key at https://apps.db.ripe.net/db-web-ui/api-keys and link
        # it to your maintainer via an auth: SSO attribute. Accepts 'keyId:password',
        # a base64 blob, or the full 'Basic <base64>' header value.
        'ripe_whois_api_token': 'YOUR_DB_API_KEY',
        'templates_dir':       '/opt/netbox/ripe_templates',

        # --- My Resources import (inbound) ---
        'lir_portal_api_key':  'YOUR_LIR_PORTAL_KEY',  # LIR Portal → API Keys → Portal key

        # --- RIPE Database import (inbound, inverse lookup) ---
        'ripe_db_maintainers': ['YOUR-MNT'],           # mnt-by names to discover objects for
        'ripe_db_orgs':        ['ORG-XXXX-RIPE'],      # and/or org ids

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

## Authentication

### RIPE Database write key (`ripe_whois_api_token`)

All **writes** to the RIPE Database — both the automatic outbound sync and the
confirmed pushes of locally-edited objects — authenticate with a RIPE Database
API key. Generate one at
[apps.db.ripe.net/db-web-ui/api-keys](https://apps.db.ripe.net/db-web-ui/api-keys)
and link your RIPE NCC Access account to the object's maintainer via an
`auth: SSO` attribute. The key is shown once; copy either the combined value or
the key-id + password.

Set it as `ripe_whois_api_token`. The plugin accepts any of the forms the RIPE
UI offers and sends it as HTTP Basic Auth:

```http
Authorization: Basic base64(key_id:password)
```

Accepted config values: `keyId:password`, a pre-encoded base64 blob, or the full
`Basic <base64>` header value. If `ripe_whois_api_token` is unset, the plugin
falls back to the legacy `ripe_api_key_id` / `ripe_api_key_secret` pair.

Reads (importing/querying the RIPE Database) are anonymous and need no key.

### LIR Portal API Key (My Resources import)

Generate a **Portal** API key in the LIR Portal under
**My Account → API Keys → Create a new LIR Portal key**.

The plugin sends it as a single header:

```http
ncc-api-authorization: YOUR_LIR_PORTAL_KEY
```

---

## My Resources Import

### Via the NetBox UI

Navigate to **RIPE Sync → Import Runs** and click **Import Now**.
A modal lets you choose:

- **Dry run** — log what would be created without actually creating anything
- **Resource types** — comma-separated subset (leave blank for all):
  `asns`, `ipv4_allocations`, `ipv4_assignments`, `ipv4_legacy`,
  `ipv6_allocations`, `ipv6_assignments`

The import runs in the background; refresh the list to see results.

### Via the management command

Runs synchronously in the current process — no RQ worker needed:

```bash
# Import everything
python manage.py ripe_import_resources

# Preview without making changes
python manage.py ripe_import_resources --dry-run

# Import only ASNs and IPv4 allocations
python manage.py ripe_import_resources --only asns ipv4_allocations
```

### NetBox object mapping

| My Resources type | NetBox object |
| --- | --- |
| ASNs | `ipam.ASN` (linked to RIPE NCC RIR) |
| IPv4 / IPv6 allocations | `ipam.Aggregate` |
| IPv4 legacy / ERX resources | `ipam.Aggregate` |
| IPv4 / IPv6 assignments | `ipam.Prefix` |

Existing objects are never modified; they are counted as *skipped*.

---

## RIPE Database Import

Where the My Resources import covers your allocations/assignments via the LIR
Portal, this import queries the RIPE Database directly and pulls in **every
object referencing your maintainer(s) or organisation(s)** — including
assignments and route objects that My Resources does not expose.

Configure the lookup targets in `PLUGINS_CONFIG`:

```python
'ripe_db_maintainers': ['YOUR-MNT'],      # inverse lookup on mnt-by
'ripe_db_orgs':        ['ORG-XXXX-RIPE'], # inverse lookup on org
```

The `source` (RIPE / TEST) follows the `ripe_db` setting, so this hits the same
database the outbound sync writes to. No API key is required for read access.

### Via the NetBox UI

Navigate to **RIPE Sync → Import Runs** and click **Import RIPE Database**.
The modal offers a dry-run toggle and an object-type filter
(`inetnum`, `inet6num`, `route`, `route6`, `domain`).

Imported objects are browsable under **RIPE Sync → Inetnum Objects**,
**Route Objects** and **Domain Objects**.

### Via the management command

```bash
# Import everything for the configured maintainers/orgs
python manage.py ripe_import_db

# Preview without making changes
python manage.py ripe_import_db --dry-run

# Import only inetnum objects and route objects
python manage.py ripe_import_db --only inetnum route
```

### NetBox object mapping

| RIPE Database object | NetBox object |
| --- | --- |
| `inetnum` / `inet6num`, status `ALLOCATED*` | `ipam.Aggregate` (+ editable `RipeInetnumObject` mirror) |
| `inetnum` / `inet6num`, other statuses (`ASSIGNED*`, …) | `ipam.Prefix` (+ editable `RipeInetnumObject` mirror) |
| `route` / `route6` | `netbox_ripe_sync.RipeRouteObject` (+ Prefix link) |
| `domain` | `netbox_ripe_sync.RipeDomainObject` |

IPv4 `inetnum` ranges that do not align to a single CIDR are split into the
minimal set of covering CIDRs. Existing objects are never modified; they are
counted as *skipped* (their editable mirror is still refreshed).

---

## Editing & Pushing Changes

Imported RIPE objects can be edited in NetBox and pushed back to the RIPE
Database. The push is deliberately decoupled from editing:

1. **Edit** — open an inetnum, route or domain object and click **Edit**. A
   structured, per-type form (e.g. nameservers for domains, descr/origin for
   routes, netname/status/org for inetnums) is pre-filled from the last-known
   RIPE state.
2. **Queue** — saving the form does **not** touch RIPE. It records a *pending
   change* (a `RipeChange`) holding the proposed RPSL attributes and a diff.
   A **Request delete** button likewise queues a deletion.
3. **Review** — **RIPE Sync → Pending Changes** lists every queued change with
   its diff and status (pending / pushed / failed / cancelled).
4. **Confirm & push** — opening a pending change shows **Push to RIPE…**, which
   requires an explicit confirmation in a modal before the API write happens.
   The result (success/failure, RIPE response, who/when) is recorded on the
   change, and the object's stored state is updated on success.

Pushing authenticates with the RIPE Database **write** API key
(`ripe_whois_api_token`) and writes to the database selected by `ripe_db`
(`TEST` or `RIPE`). inetnum pushes send the edited attributes directly and do
**not** use the template engine. Read/query operations (import, overlap search)
remain anonymous and need no key.

---

## Custom Fields (outbound sync)

| Field | Model | Type | Purpose |
| --- | --- | --- | --- |
| `ripe_report` | `ipam.Prefix` | Boolean | Enable RIPE sync for this prefix |
| `ripe_template` | `ipam.Prefix` | Text | Template key from `templates.json` |
| `lir` | `ipam.Aggregate` | Text | LIR slug, maps to RIPE org via `lir_org.json` |

---

## Template Files (outbound sync)

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
alpha-2 country code. Either:

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
