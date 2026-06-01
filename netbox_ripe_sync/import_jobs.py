"""RQ background job for the My Resources import."""

import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger('netbox.plugins.ripe_sync')


def run_my_resources_import(run_id, dry_run=False, resource_types=None, triggered_by=None):
    """Import RIPE My Resources into NetBox.

    Called by django-rq.  Updates the RipeImportRun record throughout execution
    so the UI reflects live progress.

    Args:
        run_id:         Primary key of the pre-created RipeImportRun record.
        dry_run:        When True, no objects are created in NetBox.
        resource_types: List of resource category names, or None for all.
        triggered_by:   Username string for audit.
    """
    from .models import RipeImportRun
    from .my_resources_client import MyResourcesClient, MyResourcesError
    from .importer import ResourceImporter

    try:
        run = RipeImportRun.objects.get(pk=run_id)
    except RipeImportRun.DoesNotExist:
        logger.error(f'RipeImportRun {run_id} not found — aborting job')
        return

    logger.info(
        f'Starting My Resources import (run={run_id}, dry_run={dry_run}, '
        f'resource_types={resource_types}, triggered_by={triggered_by!r})'
    )

    try:
        client = MyResourcesClient()
        resources = client.get_all()

        importer = ResourceImporter(dry_run=dry_run, resource_types=resource_types)
        stats = importer.run(resources)

        _update_run(run, stats, status=RipeImportRun.STATUS_SUCCESS)
        logger.info(
            f'My Resources import complete (run={run_id}): '
            f'created={stats.total_created()}, skipped={stats.total_skipped()}, '
            f'errors={stats.total_errors()}'
        )


    except MyResourcesError as exc:
        logger.error(f'My Resources import failed (run={run_id}): {exc}')
        run.status = RipeImportRun.STATUS_FAILED
        run.error_message = str(exc)
        run.finished = datetime.now(tz=timezone.utc)
        run.save(update_fields=['status', 'error_message', 'finished'])
        raise

    except Exception as exc:
        logger.exception(f'Unexpected error in My Resources import (run={run_id})')
        run.status = RipeImportRun.STATUS_FAILED
        run.error_message = f'{type(exc).__name__}: {exc}'
        run.finished = datetime.now(tz=timezone.utc)
        run.save(update_fields=['status', 'error_message', 'finished'])
        raise


def run_ripe_db_import(run_id, dry_run=False, object_types=None, triggered_by=None):
    """Import objects discovered in the RIPE Database via inverse lookups.

    Mirrors :func:`run_my_resources_import` but sources its data from the RIPE
    Database REST search API rather than the LIR Portal My Resources API.

    Args:
        run_id:       Primary key of the pre-created RipeImportRun record.
        dry_run:      When True, no objects are created in NetBox.
        object_types: List of object types (inetnum/inet6num/route/route6), or None.
        triggered_by: Username string for audit.
    """
    from .models import RipeImportRun
    from .ripe_db_client import RipeDbSearchClient, RipeDbSearchError
    from .importer import RipeDbImporter

    try:
        run = RipeImportRun.objects.get(pk=run_id)
    except RipeImportRun.DoesNotExist:
        logger.error(f'RipeImportRun {run_id} not found — aborting job')
        return

    logger.info(
        f'Starting RIPE Database import (run={run_id}, dry_run={dry_run}, '
        f'object_types={object_types}, triggered_by={triggered_by!r})'
    )

    try:
        client = RipeDbSearchClient()
        objects = client.get_all(object_types=object_types)

        importer = RipeDbImporter(dry_run=dry_run, resource_types=object_types)
        stats = importer.run(objects)

        _update_run(run, stats, status=RipeImportRun.STATUS_SUCCESS)
        logger.info(
            f'RIPE Database import complete (run={run_id}): '
            f'created={stats.total_created()}, skipped={stats.total_skipped()}, '
            f'errors={stats.total_errors()}'
        )

    except RipeDbSearchError as exc:
        logger.error(f'RIPE Database import failed (run={run_id}): {exc}')
        run.status = RipeImportRun.STATUS_FAILED
        run.error_message = str(exc)
        run.finished = datetime.now(tz=timezone.utc)
        run.save(update_fields=['status', 'error_message', 'finished'])
        raise

    except Exception as exc:
        logger.exception(f'Unexpected error in RIPE Database import (run={run_id})')
        run.status = RipeImportRun.STATUS_FAILED
        run.error_message = f'{type(exc).__name__}: {exc}'
        run.finished = datetime.now(tz=timezone.utc)
        run.save(update_fields=['status', 'error_message', 'finished'])
        raise


def _update_run(run, stats, status):
    from datetime import datetime, timezone
    d = stats.as_dict()
    run.status = status
    run.finished = datetime.now(tz=timezone.utc)
    for field, value in d.items():
        setattr(run, field, value)
    if stats.errors:
        run.error_detail = json.dumps(stats.errors)
    run.save()
