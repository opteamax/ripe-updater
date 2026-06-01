from rest_framework import serializers

from ..models import (
    RipeSyncLog,
    RipeRouteObject,
    RipeDomainObject,
    RipeInetnumObject,
    RipeChange,
)


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


class RipeRouteObjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = RipeRouteObject
        fields = [
            'id',
            'prefix',
            'origin',
            'is_ipv6',
            'maintainer',
            'source',
            'description',
            'netbox_prefix',
            'created',
            'last_updated',
        ]
        read_only_fields = fields


class RipeDomainObjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = RipeDomainObject
        fields = [
            'id', 'domain', 'description', 'admin_c', 'tech_c', 'zone_c',
            'nameservers', 'maintainer', 'source', 'local_status',
            'last_imported', 'last_pushed', 'created', 'last_updated',
        ]
        read_only_fields = fields


class RipeInetnumObjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = RipeInetnumObject
        fields = [
            'id', 'prefix', 'ripe_primary_key', 'is_ipv6', 'netname', 'description',
            'country', 'status', 'org', 'maintainer', 'source', 'local_status',
            'netbox_prefix', 'netbox_aggregate',
            'last_imported', 'last_pushed', 'created', 'last_updated',
        ]
        read_only_fields = fields


class RipeChangeSerializer(serializers.ModelSerializer):
    operation_display = serializers.CharField(source='get_operation_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = RipeChange
        fields = [
            'id', 'object_type', 'primary_key', 'operation', 'operation_display',
            'status', 'status_display', 'proposed_attributes', 'diff',
            'requested_by', 'requested_at', 'pushed_by', 'pushed_at',
            'error_message',
        ]
        read_only_fields = fields


class TriggerSyncSerializer(serializers.Serializer):
    prefix_id = serializers.IntegerField(help_text='NetBox Prefix primary key')
