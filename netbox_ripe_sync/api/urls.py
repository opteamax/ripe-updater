from rest_framework.routers import DefaultRouter
from django.urls import path

from .views import RipeSyncLogViewSet, TriggerSyncView

router = DefaultRouter()
router.register(r'logs', RipeSyncLogViewSet, basename='ripesyncclog')

urlpatterns = router.urls + [
    path('sync/', TriggerSyncView.as_view(), name='trigger_sync'),
]
