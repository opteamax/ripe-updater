import logging

logger = logging.getLogger('netbox.plugins.ripe_sync')


def run_ripe_sync(prefix_str, action, template=None, country=None, org=None, triggered_by=None):
    """RQ job: queue a prefix change for review instead of pushing to RIPE.

    Historically this pushed directly to the RIPE Database. It now generates the
    intended inetnum/inet6num object and records it as a *pending* ``RipeChange``
    (a "task to write") that a human must review and confirm before anything is
    sent to RIPE. Nothing here writes to the RIPE Database.

    All required data is supplied at enqueue time so the job never queries NetBox
    for context beyond linking the local mirror object.
    """
    from .exceptions import NotRoutablePrefix, PrefixTooSmall, RipeSyncException
    from .models import RipeSyncLog

    logger.info(f'Queuing RIPE task: {action} {prefix_str} (triggered_by={triggered_by!r})')

    try:
        message = _build_prefix_change(prefix_str, action, template, country, org, triggered_by)
        RipeSyncLog.objects.create(
            prefix=prefix_str,
            action=action,
            status=RipeSyncLog.STATUS_QUEUED,
            triggered_by=triggered_by or '',
            ripe_response=message,
        )
        logger.info(f'RIPE task queued: {action} {prefix_str} — {message}')

    except (NotRoutablePrefix, PrefixTooSmall) as exc:
        # Not an error — prefix is intentionally outside RIPE scope
        RipeSyncLog.objects.create(
            prefix=prefix_str,
            action=action,
            status=RipeSyncLog.STATUS_SKIPPED,
            triggered_by=triggered_by or '',
            ripe_response=str(exc),
        )
        logger.info(f'RIPE task skipped: {prefix_str} — {exc}')

    except RipeSyncException as exc:
        RipeSyncLog.objects.create(
            prefix=prefix_str,
            action=action,
            status=RipeSyncLog.STATUS_FAILED,
            triggered_by=triggered_by or '',
            error_message=str(exc),
        )
        logger.error(f'RIPE task failed: {action} {prefix_str} — {exc}')
        raise

    except Exception as exc:
        RipeSyncLog.objects.create(
            prefix=prefix_str,
            action=action,
            status=RipeSyncLog.STATUS_FAILED,
            triggered_by=triggered_by or '',
            error_message=f'{type(exc).__name__}: {exc}',
        )
        logger.exception(f'Unexpected error queuing RIPE task for {prefix_str}')
        raise


def _build_prefix_change(prefix_str, action, template, country, org, triggered_by):
    """Create or update the pending RipeChange for a NetBox prefix. Returns a message."""
    from django.contrib.contenttypes.models import ContentType

    from .config import get_config
    from .forms import attributes_to_fields, diff_attributes
    from .models import RipeChange, RipeInetnumObject, RipeSyncLog
    from .prefix_utils import find, format_cidr
    from .ripe_client import RipeClient

    # RipeClient.__init__ validates the prefix (raises NotRoutablePrefix /
    # PrefixTooSmall for out-of-scope prefixes, which the caller treats as skip).
    client = RipeClient(prefix_str, template, country, org)
    object_type = client.objecttype  # 'inet6num' or 'inetnum'
    is_v6 = object_type == 'inet6num'
    primary_key = prefix_str if is_v6 else format_cidr(prefix_str)
    source = get_config('ripe_db')

    delete = action == RipeSyncLog.ACTION_DELETE

    # Inspect the current RIPE state so we know create-vs-modify and can diff.
    existing = client._get_existing()
    existing_attrs = _extract_attrs(find('objects.object', existing)) if existing else []

    if delete:
        operation = RipeChange.OP_DELETE
        proposed = existing_attrs
    else:
        if not template:
            from .exceptions import RipeAPIError
            raise RipeAPIError(f'No RIPE template configured for {prefix_str}')
        generated = client._engine.generate_object(
            prefix_str, template, org, country, client.status
        )
        proposed = _extract_attrs(find('objects.object', generated))
        operation = RipeChange.OP_MODIFY if existing else RipeChange.OP_CREATE

    # Upsert the local editable mirror (last-known RIPE state).
    known_attrs = existing_attrs
    fields = attributes_to_fields('inetnum', known_attrs or proposed)
    mirror, _ = RipeInetnumObject.objects.update_or_create(
        ripe_primary_key=primary_key,
        source=source,
        defaults=dict(
            prefix=prefix_str,
            is_ipv6=is_v6,
            raw_attributes=known_attrs,
            local_status=(RipeInetnumObject.STATUS_IN_SYNC if existing
                          else RipeInetnumObject.STATUS_LOCAL),
            **fields,
        ),
    )
    _link_netbox_prefix(mirror, prefix_str)
    mirror.save()

    # Build the human-readable diff + the My Resources membership note.
    if delete:
        diff = '\n'.join(f'- {a.get("name")}: {a.get("value")}' for a in proposed)
    else:
        diff = diff_attributes(known_attrs, proposed)

    member, parent = _safe_membership(prefix_str)
    if member is None:
        note = 'My Resources membership: could not verify (will be re-checked at push).'
    elif member:
        note = f'My Resources membership: OK (within {parent}).'
    else:
        note = ('My Resources membership: NOT a member — the push will be refused '
                'unless require_my_resources_membership is disabled.')

    # Replace any existing pending change of the same operation for this object.
    change, created = RipeChange.objects.update_or_create(
        content_type=ContentType.objects.get_for_model(RipeInetnumObject),
        object_id=mirror.pk,
        operation=operation,
        status=RipeChange.STATUS_PENDING,
        defaults=dict(
            object_type=object_type,
            primary_key=primary_key,
            proposed_attributes=proposed,
            diff=f'{diff}\n\n{note}' if diff else note,
            requested_by=triggered_by or '',
        ),
    )
    verb = 'Created' if created else 'Updated'
    return f'{verb} pending change #{change.pk} ({operation}) for review. {note}'


def _extract_attrs(objects):
    """Pull [{'name','value'}, ...] from a RIPE REST objects.object list."""
    if not objects:
        return []
    attrs = (((objects[0] or {}).get('attributes') or {}).get('attribute')) or []
    return [{'name': a.get('name', ''), 'value': a.get('value', '')} for a in attrs]


def _link_netbox_prefix(mirror, prefix_str):
    try:
        from ipam.models import Aggregate, Prefix
        mirror.netbox_prefix = Prefix.objects.filter(prefix=prefix_str).first()
        mirror.netbox_aggregate = Aggregate.objects.filter(prefix=prefix_str).first()
    except Exception as exc:  # noqa: BLE001
        logger.debug(f'Could not link NetBox object for {prefix_str}: {exc}')


def _safe_membership(prefix_str):
    """Return (is_member|None, parent). None means the check could not run."""
    from .resource_check import prefix_within_my_resources
    try:
        return prefix_within_my_resources(prefix_str)
    except Exception as exc:  # noqa: BLE001 - advisory at queue time
        logger.warning(f'My Resources membership check unavailable for {prefix_str}: {exc}')
        return None, None
