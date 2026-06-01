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
    path('import/trigger-db/', views.TriggerDbImportView.as_view(), name='trigger_db_import'),
    path('routes/', views.RipeRouteObjectListView.as_view(), name='riperouteobject_list'),
    path('routes/<int:pk>/', views.RipeRouteObjectDetailView.as_view(), name='riperouteobject'),
    path('domains/', views.RipeDomainObjectListView.as_view(), name='ripedomainobject_list'),
    path('domains/<int:pk>/', views.RipeDomainObjectDetailView.as_view(), name='ripedomainobject'),
    path('inetnums/', views.RipeInetnumObjectListView.as_view(), name='ripeinetnumobject_list'),
    path('inetnums/<int:pk>/', views.RipeInetnumObjectDetailView.as_view(), name='ripeinetnumobject'),
    # Local-edit workflow
    path('edit/<str:kind>/<int:pk>/', views.RipeObjectEditView.as_view(), name='ripeobject_edit'),
    path('delete/<str:kind>/<int:pk>/', views.RipeObjectDeleteRequestView.as_view(), name='ripeobject_delete'),
    path('changes/', views.RipeChangeListView.as_view(), name='ripechange_list'),
    path('changes/<int:pk>/', views.RipeChangeDetailView.as_view(), name='ripechange'),
    path('changes/<int:pk>/push/', views.RipeChangePushView.as_view(), name='ripechange_push'),
    path('changes/<int:pk>/cancel/', views.RipeChangeCancelView.as_view(), name='ripechange_cancel'),
]
