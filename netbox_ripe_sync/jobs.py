import logging

logger = logging.getLogger('netbox.plugins.ripe_sync')


def run_ripe_sync(prefix_str, action, template=None, country=None, org=None, triggered_by=None):
    """RQ job: synchronise one prefix to the RIPE Database.

    Called by signal handlers via django-rq.  All required data is supplied
    at enqueue time so the job is self-contained and never queries NetBox.
    """
    from .exceptions import NotRoutablePrefix, PrefixTooSmall, RipeSyncException
    from .models import RipeSyncLog
    from .ripe_client import RipeClient

    logger.info(f'Starting RIPE sync: {action} {prefix_str} (triggered_by={triggered_by!r})')

    try:
        client = RipeClient(prefix_str, template, country, org)

        if action == RipeSyncLog.ACTION_DELETE:
            result = client.delete()
        else:
            result = client.push()

        RipeSyncLog.objects.create(
            prefix=prefix_str,
            action=action,
            status=RipeSyncLog.STATUS_SUCCESS,
            triggered_by=triggered_by or '',
            ripe_response=result,
        )
        logger.info(f'RIPE sync succeeded: {action} {prefix_str}')

    except (NotRoutablePrefix, PrefixTooSmall) as exc:
        # Not an error — prefix is intentionally outside RIPE scope
        RipeSyncLog.objects.create(
            prefix=prefix_str,
            action=action,
            status=RipeSyncLog.STATUS_SKIPPED,
            triggered_by=triggered_by or '',
            ripe_response=str(exc),
        )
        logger.info(f'RIPE sync skipped: {prefix_str} — {exc}')

    except RipeSyncException as exc:
        RipeSyncLog.objects.create(
            prefix=prefix_str,
            action=action,
            status=RipeSyncLog.STATUS_FAILED,
            triggered_by=triggered_by or '',
            error_message=str(exc),
        )
        logger.error(f'RIPE sync failed: {action} {prefix_str} — {exc}')
        raise  # let RQ mark the job as failed

    except Exception as exc:
        RipeSyncLog.objects.create(
            prefix=prefix_str,
            action=action,
            status=RipeSyncLog.STATUS_FAILED,
            triggered_by=triggered_by or '',
            error_message=f'{type(exc).__name__}: {exc}',
        )
        logger.exception(f'Unexpected error in RIPE sync for {prefix_str}')
        raise
