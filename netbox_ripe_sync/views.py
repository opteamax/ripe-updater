import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views import View
from django_tables2 import SingleTableMixin
from django.views.generic import DetailView, ListView

from .models import (
    RipeSyncLog,
    RipeImportRun,
    RipeRouteObject,
    RipeDomainObject,
    RipeInetnumObject,
    RipeChange,
)
from .tables import (
    RipeSyncLogTable,
    RipeImportRunTable,
    RipeRouteObjectTable,
    RipeDomainObjectTable,
    RipeInetnumObjectTable,
    RipeChangeTable,
)

logger = logging.getLogger('netbox.plugins.ripe_sync')


class RipeSyncLogListView(LoginRequiredMixin, SingleTableMixin, ListView):
    model = RipeSyncLog
    table_class = RipeSyncLogTable
    template_name = 'netbox_ripe_sync/ripesyncclog_list.html'
    context_object_name = 'logs'
    paginate_by = 50

    def get_queryset(self):
        qs = RipeSyncLog.objects.order_by('-created')
        prefix_filter = self.request.GET.get('prefix')
        if prefix_filter:
            qs = qs.filter(prefix=prefix_filter)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['prefix_filter'] = self.request.GET.get('prefix', '')
        return ctx


class RipeSyncLogDetailView(LoginRequiredMixin, DetailView):
    model = RipeSyncLog
    template_name = 'netbox_ripe_sync/ripesyncclog_detail.html'
    context_object_name = 'log'


class ManualSyncView(LoginRequiredMixin, View):
    """Manually enqueue a RIPE sync for a specific prefix."""

    def post(self, request, pk):
        from ipam.models import Prefix
        from .signals import _collect_and_enqueue
        from .models import RipeSyncLog

        prefix = get_object_or_404(Prefix, pk=pk)

        if not prefix.custom_field_data.get('ripe_report'):
            messages.warning(
                request,
                f'ripe_report is not enabled for {prefix.prefix}. Enable it first.'
            )
            return HttpResponseRedirect(prefix.get_absolute_url())

        try:
            _collect_and_enqueue(prefix, RipeSyncLog.ACTION_UPDATE)
            messages.success(request, f'RIPE sync queued for {prefix.prefix}.')
        except Exception as exc:
            logger.exception(f'Manual sync failed for {prefix.prefix}')
            messages.error(request, f'Failed to queue RIPE sync: {exc}')

        return HttpResponseRedirect(prefix.get_absolute_url())


class RipeImportRunListView(LoginRequiredMixin, SingleTableMixin, ListView):
    model = RipeImportRun
    table_class = RipeImportRunTable
    template_name = 'netbox_ripe_sync/ripeimportrun_list.html'
    context_object_name = 'runs'
    paginate_by = 25

    def get_queryset(self):
        return RipeImportRun.objects.order_by('-started')


class RipeImportRunDetailView(LoginRequiredMixin, DetailView):
    model = RipeImportRun
    template_name = 'netbox_ripe_sync/ripeimportrun_detail.html'
    context_object_name = 'run'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['error_detail'] = self.object.get_error_detail()
        return ctx


class TriggerImportView(LoginRequiredMixin, View):
    """Create a RipeImportRun record and enqueue the background import job."""

    def post(self, request):
        import django_rq
        from datetime import datetime, timezone
        from .import_jobs import run_my_resources_import

        dry_run = request.POST.get('dry_run') == '1'
        only_raw = request.POST.get('resource_types', '').strip()
        resource_types = [t.strip() for t in only_raw.split(',') if t.strip()] or None

        run = RipeImportRun.objects.create(
            status=RipeImportRun.STATUS_RUNNING,
            source=RipeImportRun.SOURCE_MY_RESOURCES,
            triggered_by=request.user.username,
            dry_run=dry_run,
        )

        try:
            queue = django_rq.get_queue('default')
            queue.enqueue(
                run_my_resources_import,
                run_id=run.pk,
                dry_run=dry_run,
                resource_types=resource_types,
                triggered_by=request.user.username,
            )
            label = 'Dry-run' if dry_run else 'Import'
            messages.success(request, f'{label} job queued (run #{run.pk}).')
        except Exception as exc:
            logger.exception('Failed to enqueue import job')
            run.status = RipeImportRun.STATUS_FAILED
            run.error_message = str(exc)
            run.finished = datetime.now(tz=timezone.utc)
            run.save(update_fields=['status', 'error_message', 'finished'])
            messages.error(request, f'Failed to queue import: {exc}')

        return HttpResponseRedirect(reverse('plugins:netbox_ripe_sync:ripeimportrun_list'))


class TriggerDbImportView(LoginRequiredMixin, View):
    """Create a RipeImportRun and enqueue the RIPE Database inverse-lookup import."""

    def post(self, request):
        import django_rq
        from datetime import datetime, timezone
        from .import_jobs import run_ripe_db_import

        dry_run = request.POST.get('dry_run') == '1'
        only_raw = request.POST.get('object_types', '').strip()
        object_types = [t.strip() for t in only_raw.split(',') if t.strip()] or None

        run = RipeImportRun.objects.create(
            status=RipeImportRun.STATUS_RUNNING,
            source=RipeImportRun.SOURCE_RIPE_DB,
            triggered_by=request.user.username,
            dry_run=dry_run,
        )

        try:
            queue = django_rq.get_queue('default')
            queue.enqueue(
                run_ripe_db_import,
                run_id=run.pk,
                dry_run=dry_run,
                object_types=object_types,
                triggered_by=request.user.username,
            )
            label = 'Dry-run' if dry_run else 'Import'
            messages.success(request, f'{label} job queued (run #{run.pk}).')
        except Exception as exc:
            logger.exception('Failed to enqueue RIPE Database import job')
            run.status = RipeImportRun.STATUS_FAILED
            run.error_message = str(exc)
            run.finished = datetime.now(tz=timezone.utc)
            run.save(update_fields=['status', 'error_message', 'finished'])
            messages.error(request, f'Failed to queue import: {exc}')

        return HttpResponseRedirect(reverse('plugins:netbox_ripe_sync:ripeimportrun_list'))


class RipeRouteObjectListView(LoginRequiredMixin, SingleTableMixin, ListView):
    model = RipeRouteObject
    table_class = RipeRouteObjectTable
    template_name = 'netbox_ripe_sync/riperouteobject_list.html'
    context_object_name = 'routes'
    paginate_by = 50

    def get_queryset(self):
        qs = RipeRouteObject.objects.all()
        prefix_filter = self.request.GET.get('prefix')
        if prefix_filter:
            qs = qs.filter(prefix=prefix_filter)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['prefix_filter'] = self.request.GET.get('prefix', '')
        return ctx


class RipeRouteObjectDetailView(LoginRequiredMixin, DetailView):
    model = RipeRouteObject
    template_name = 'netbox_ripe_sync/riperouteobject_detail.html'
    context_object_name = 'route'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['kind'] = 'route'
        ctx['pending'] = self.object.pending_changes()
        return ctx


class RipeDomainObjectListView(LoginRequiredMixin, SingleTableMixin, ListView):
    model = RipeDomainObject
    table_class = RipeDomainObjectTable
    template_name = 'netbox_ripe_sync/ripedomainobject_list.html'
    context_object_name = 'domains'
    paginate_by = 50


class RipeDomainObjectDetailView(LoginRequiredMixin, DetailView):
    model = RipeDomainObject
    template_name = 'netbox_ripe_sync/ripedomainobject_detail.html'
    context_object_name = 'domain'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['kind'] = 'domain'
        ctx['pending'] = self.object.pending_changes()
        return ctx


class RipeInetnumObjectListView(LoginRequiredMixin, SingleTableMixin, ListView):
    model = RipeInetnumObject
    table_class = RipeInetnumObjectTable
    template_name = 'netbox_ripe_sync/ripeinetnumobject_list.html'
    context_object_name = 'inetnums'
    paginate_by = 50


class RipeInetnumObjectDetailView(LoginRequiredMixin, DetailView):
    model = RipeInetnumObject
    template_name = 'netbox_ripe_sync/ripeinetnumobject_detail.html'
    context_object_name = 'inetnum'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['kind'] = 'inetnum'
        ctx['pending'] = self.object.pending_changes()
        return ctx


# ----------------------------------------------------------------------
# Local-edit workflow: edit → changeset → confirmed push
# ----------------------------------------------------------------------

# Maps the URL 'kind' segment to its model. inetnum covers inet6num too.
_KIND_MODELS = {
    'route': RipeRouteObject,
    'domain': RipeDomainObject,
    'inetnum': RipeInetnumObject,
}


def _kind_for_object_type(object_type):
    if object_type in ('route', 'route6'):
        return 'route'
    if object_type in ('inetnum', 'inet6num'):
        return 'inetnum'
    return 'domain'


class RipeObjectEditView(LoginRequiredMixin, View):
    """Render the per-type edit form and queue the result as a pending change."""

    template_name = 'netbox_ripe_sync/ripeobject_edit.html'

    def _resolve(self, kind):
        from .forms import FORM_REGISTRY
        model = _KIND_MODELS.get(kind)
        form_cls = FORM_REGISTRY.get(kind)
        if model is None or form_cls is None:
            raise Http404(f'Unknown object kind {kind!r}')
        return model, form_cls

    def get(self, request, kind, pk):
        from django.shortcuts import render
        model, form_cls = self._resolve(kind)
        obj = get_object_or_404(model, pk=pk)
        form = form_cls(instance=obj)
        return render(request, self.template_name, {'form': form, 'obj': obj, 'kind': kind})

    def post(self, request, kind, pk):
        from django.shortcuts import render
        from django.contrib.contenttypes.models import ContentType
        from .forms import diff_attributes

        model, form_cls = self._resolve(kind)
        obj = get_object_or_404(model, pk=pk)
        form = form_cls(request.POST, instance=obj)
        if not form.is_valid():
            return render(request, self.template_name, {'form': form, 'obj': obj, 'kind': kind})

        proposed = form.proposed_attributes()
        diff = diff_attributes(obj.raw_attributes or [], proposed)
        if not diff:
            messages.info(request, 'No changes detected — nothing was queued.')
            return HttpResponseRedirect(obj.get_absolute_url())

        change = RipeChange.objects.create(
            content_type=ContentType.objects.get_for_model(model),
            object_id=obj.pk,
            object_type=obj.object_type,
            primary_key=obj.ripe_primary_key or str(obj),
            operation=RipeChange.OP_MODIFY,
            proposed_attributes=proposed,
            diff=diff,
            status=RipeChange.STATUS_PENDING,
            requested_by=request.user.username,
        )
        messages.success(
            request,
            f'Change #{change.pk} queued. Review and confirm it to push to RIPE.',
        )
        return HttpResponseRedirect(change.get_absolute_url())


class RipeObjectDeleteRequestView(LoginRequiredMixin, View):
    """Queue a pending change that will DELETE the object from RIPE on push."""

    def post(self, request, kind, pk):
        from django.contrib.contenttypes.models import ContentType
        model = _KIND_MODELS.get(kind)
        if model is None:
            raise Http404(f'Unknown object kind {kind!r}')
        obj = get_object_or_404(model, pk=pk)

        change = RipeChange.objects.create(
            content_type=ContentType.objects.get_for_model(model),
            object_id=obj.pk,
            object_type=obj.object_type,
            primary_key=obj.ripe_primary_key or str(obj),
            operation=RipeChange.OP_DELETE,
            proposed_attributes=obj.raw_attributes or [],
            diff='\n'.join(f'- {a.get("name")}: {a.get("value")}' for a in (obj.raw_attributes or [])),
            status=RipeChange.STATUS_PENDING,
            requested_by=request.user.username,
        )
        messages.warning(
            request,
            f'Deletion change #{change.pk} queued. Confirm it to delete from RIPE.',
        )
        return HttpResponseRedirect(change.get_absolute_url())


class RipeChangeListView(LoginRequiredMixin, SingleTableMixin, ListView):
    model = RipeChange
    table_class = RipeChangeTable
    template_name = 'netbox_ripe_sync/ripechange_list.html'
    context_object_name = 'changes'
    paginate_by = 50

    def get_queryset(self):
        qs = RipeChange.objects.all()
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['status_filter'] = self.request.GET.get('status', '')
        ctx['pending_count'] = RipeChange.objects.filter(status=RipeChange.STATUS_PENDING).count()
        return ctx


class RipeChangeDetailView(LoginRequiredMixin, DetailView):
    model = RipeChange
    template_name = 'netbox_ripe_sync/ripechange_detail.html'
    context_object_name = 'change'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['diff_lines'] = self.object.get_diff_lines()
        return ctx


class RipeChangeCancelView(LoginRequiredMixin, View):
    def post(self, request, pk):
        change = get_object_or_404(RipeChange, pk=pk)
        if change.status != RipeChange.STATUS_PENDING:
            messages.warning(request, 'Only pending changes can be cancelled.')
        else:
            change.status = RipeChange.STATUS_CANCELLED
            change.save(update_fields=['status'])
            messages.success(request, f'Change #{change.pk} cancelled.')
        return HttpResponseRedirect(reverse('plugins:netbox_ripe_sync:ripechange_list'))


class RipeChangePushView(LoginRequiredMixin, View):
    """Push a single change to RIPE. Requires an explicit confirmation field."""

    def post(self, request, pk):
        from datetime import datetime, timezone
        from .exceptions import RipeSyncException
        from .ripe_db_writer import RipeDbWriter
        from .forms import attributes_to_fields

        change = get_object_or_404(RipeChange, pk=pk)

        # Extra confirmation guard — the form must explicitly opt in.
        if request.POST.get('confirm') != '1':
            messages.warning(request, 'Push not confirmed.')
            return HttpResponseRedirect(change.get_absolute_url())

        if change.status != RipeChange.STATUS_PENDING:
            messages.warning(request, 'Only pending changes can be pushed.')
            return HttpResponseRedirect(change.get_absolute_url())

        target = change.target
        now = datetime.now(tz=timezone.utc)
        try:
            writer = RipeDbWriter()
            if change.operation == RipeChange.OP_DELETE:
                resp = writer.delete(change.object_type, change.primary_key)
            elif change.operation == RipeChange.OP_CREATE:
                resp = writer.create(change.object_type, change.proposed_attributes)
            else:
                resp = writer.modify(
                    change.object_type, change.primary_key, change.proposed_attributes
                )
        except RipeSyncException as exc:
            change.status = RipeChange.STATUS_FAILED
            change.error_message = str(exc)
            change.pushed_by = request.user.username
            change.pushed_at = now
            change.save()
            if target is not None:
                target.local_status = target.STATUS_PUSH_FAILED
                target.last_error = str(exc)
                target.save(update_fields=['local_status', 'last_error'])
            messages.error(request, f'Push failed: {exc}')
            return HttpResponseRedirect(change.get_absolute_url())

        # Success
        change.status = RipeChange.STATUS_PUSHED
        change.pushed_by = request.user.username
        change.pushed_at = now
        change.ripe_response = (resp or '')[:5000]
        change.save()

        if target is not None and change.operation != RipeChange.OP_DELETE:
            kind = _kind_for_object_type(change.object_type)
            target.raw_attributes = change.proposed_attributes
            for field, value in attributes_to_fields(kind, change.proposed_attributes).items():
                setattr(target, field, value)
            target.local_status = target.STATUS_IN_SYNC
            target.last_pushed = now
            target.last_error = ''
            target.save()

        messages.success(request, f'Change #{change.pk} pushed to RIPE.')
        return HttpResponseRedirect(change.get_absolute_url())
