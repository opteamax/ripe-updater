from rest_framework.routers import DefaultRouter
from django.urls import path

from .views import (
    RipeSyncLogViewSet,
    RipeRouteObjectViewSet,
    RipeDomainObjectViewSet,
    RipeInetnumObjectViewSet,
    RipeChangeViewSet,
    TriggerSyncView,
)

router = DefaultRouter()
router.register(r'logs', RipeSyncLogViewSet, basename='ripesyncclog')
router.register(r'route-objects', RipeRouteObjectViewSet, basename='riperouteobject')
router.register(r'domain-objects', RipeDomainObjectViewSet, basename='ripedomainobject')
router.register(r'inetnum-objects', RipeInetnumObjectViewSet, basename='ripeinetnumobject')
router.register(r'changes', RipeChangeViewSet, basename='ripechange')

urlpatterns = router.urls + [
    path('sync/', TriggerSyncView.as_view(), name='trigger_sync'),
]
