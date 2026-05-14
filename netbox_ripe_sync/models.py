import json

from django.db import models


class RipeSyncLog(models.Model):
    ACTION_CREATE = 'create'
    ACTION_UPDATE = 'update'
    ACTION_DELETE = 'delete'
    ACTION_CHOICES = [
        (ACTION_CREATE, 'Create'),
        (ACTION_UPDATE, 'Update'),
        (ACTION_DELETE, 'Delete'),
    ]

    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_SKIPPED = 'skipped'
    STATUS_CHOICES = [
        (STATUS_SUCCESS, 'Success'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_SKIPPED, 'Skipped'),
    ]

    prefix = models.CharField(max_length=50, db_index=True)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    triggered_by = models.CharField(max_length=150, blank=True)
    ripe_response = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    created = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        app_label = 'netbox_ripe_sync'
        ordering = ['-created']

    def __str__(self):
        return f'{self.prefix} {self.action} ({self.status}) @ {self.created:%Y-%m-%d %H:%M}'

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('plugins:netbox_ripe_sync:ripesyncclog', args=[self.pk])

    @property
    def status_badge(self):
        return {
            self.STATUS_SUCCESS: 'success',
            self.STATUS_FAILED: 'danger',
            self.STATUS_SKIPPED: 'warning',
        }.get(self.status, 'secondary')


class RipeImportRun(models.Model):
    """Records one complete run of the My Resources import job."""

    STATUS_RUNNING = 'running'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_RUNNING, 'Running'),
        (STATUS_SUCCESS, 'Success'),
        (STATUS_FAILED, 'Failed'),
    ]

    started = models.DateTimeField(auto_now_add=True, db_index=True)
    finished = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_RUNNING)
    triggered_by = models.CharField(max_length=150, blank=True)
    dry_run = models.BooleanField(default=False)

    # Per-type counters
    asns_created = models.IntegerField(default=0)
    asns_skipped = models.IntegerField(default=0)
    asns_errors = models.IntegerField(default=0)
    aggregates_created = models.IntegerField(default=0)
    aggregates_skipped = models.IntegerField(default=0)
    aggregates_errors = models.IntegerField(default=0)
    prefixes_created = models.IntegerField(default=0)
    prefixes_skipped = models.IntegerField(default=0)
    prefixes_errors = models.IntegerField(default=0)

    error_message = models.TextField(blank=True)
    # JSON array of (resource_type, identifier, message) tuples for per-resource errors
    error_detail = models.TextField(blank=True)

    class Meta:
        app_label = 'netbox_ripe_sync'
        ordering = ['-started']

    def __str__(self):
        ts = self.started.strftime('%Y-%m-%d %H:%M')
        label = '[DRY RUN] ' if self.dry_run else ''
        return f'{label}Import run {ts} ({self.status})'

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('plugins:netbox_ripe_sync:ripeimportrun', args=[self.pk])

    @property
    def status_badge(self):
        return {
            self.STATUS_RUNNING: 'info',
            self.STATUS_SUCCESS: 'success',
            self.STATUS_FAILED: 'danger',
        }.get(self.status, 'secondary')

    def total_created(self):
        return self.asns_created + self.aggregates_created + self.prefixes_created

    def total_skipped(self):
        return self.asns_skipped + self.aggregates_skipped + self.prefixes_skipped

    def total_errors(self):
        return self.asns_errors + self.aggregates_errors + self.prefixes_errors

    def get_error_detail(self):
        if not self.error_detail:
            return []
        try:
            return json.loads(self.error_detail)
        except (ValueError, TypeError):
            return []
