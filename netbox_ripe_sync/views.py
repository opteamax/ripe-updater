import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views import View
from django_tables2 import SingleTableMixin
from django.views.generic import DetailView, ListView

from .models import RipeSyncLog
from .tables import RipeSyncLogTable

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
