from rest_framework import serializers

from ..models import RipeSyncLog


class RipeSyncLogSerializer(serializers.ModelSerializer):
    action_display = serializers.CharField(source='get_action_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = RipeSyncLog
        fields = [
            'id',
            'prefix',
            'action',
            'action_display',
            'status',
            'status_display',
            'triggered_by',
            'ripe_response',
            'error_message',
            'created',
        ]
        read_only_fields = fields


class TriggerSyncSerializer(serializers.Serializer):
    prefix_id = serializers.IntegerField(help_text='NetBox Prefix primary key')
