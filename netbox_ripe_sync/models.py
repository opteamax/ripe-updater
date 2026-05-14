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
