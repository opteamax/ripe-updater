import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views import View
from django_tables2 import SingleTableMixin
from django.views.generic import DetailView, ListView

from .models import RipeSyncLog, RipeImportRun
from .tables import RipeSyncLogTable, RipeImportRunTable

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
