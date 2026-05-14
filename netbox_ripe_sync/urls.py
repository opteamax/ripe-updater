from django.urls import path

from . import views

app_name = 'netbox_ripe_sync'

urlpatterns = [
    path('logs/', views.RipeSyncLogListView.as_view(), name='ripesyncclog_list'),
    path('logs/<int:pk>/', views.RipeSyncLogDetailView.as_view(), name='ripesyncclog'),
    path('sync/<int:pk>/', views.ManualSyncView.as_view(), name='manual_sync'),
    path('import/', views.RipeImportRunListView.as_view(), name='ripeimportrun_list'),
    path('import/<int:pk>/', views.RipeImportRunDetailView.as_view(), name='ripeimportrun'),
    path('import/trigger/', views.TriggerImportView.as_view(), name='trigger_import'),
]
