"""Authentication helpers for RIPE Database access.

Read/query requests to the RIPE Database REST API are anonymous. *Write*
requests (create / modify / delete of inetnum, route, domain, … objects)
require a RIPE Database API key that is linked to the object's maintainer via an
``auth: SSO`` attribute. That key is generated at
https://apps.db.ripe.net/db-web-ui/api-keys and is presented as HTTP Basic auth.

The key has two parts (key-id + password). We accept it as a single configured
token (``ripe_whois_api_token``) in any of the forms the RIPE UI offers:

* ``keyId:password``            — raw combined credential (we base64-encode it)
* ``<base64>``                  — already base64-encoded ``keyId:password``
* ``Basic <base64>``            — the full header value as shown in the UI

For backward compatibility, if no whois token is configured we fall back to the
legacy ``ripe_api_key_id`` / ``ripe_api_key_secret`` pair.
"""

import base64

from .config import get_config
from .exceptions import MissingConfig


def write_authorization() -> str:
    """Return the ``Authorization`` header *value* for RIPE Database writes."""
    token = get_config('ripe_whois_api_token')
    if token:
        token = token.strip()
        if token.lower().startswith('basic '):
            return token
        if ':' in token:
            token = base64.b64encode(token.encode()).decode()
        return f'Basic {token}'

    key_id = get_config('ripe_api_key_id')
    key_secret = get_config('ripe_api_key_secret')
    if key_id and key_secret:
        encoded = base64.b64encode(f'{key_id}:{key_secret}'.encode()).decode()
        return f'Basic {encoded}'

    raise MissingConfig(
        'ripe_whois_api_token must be set in PLUGINS_CONFIG to write to the RIPE '
        'Database. Generate a Database API key at '
        'https://apps.db.ripe.net/db-web-ui/api-keys and link it to your '
        'maintainer via an auth: SSO attribute.'
    )
