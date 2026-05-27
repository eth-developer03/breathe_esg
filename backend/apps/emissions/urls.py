from django.urls import path
from . import views

urlpatterns = [
    path('records/', views.NormalizedRecordListView.as_view(), name='records-list'),
    # bulk-approve must come before <uuid:pk>/ to avoid URL ambiguity
    path('records/bulk-approve/', views.bulk_approve, name='bulk-approve'),
    path('records/<uuid:pk>/', views.NormalizedRecordDetailView.as_view(), name='record-detail'),
    path('records/<uuid:pk>/approve/', views.approve_record, name='record-approve'),
    path('records/<uuid:pk>/reject/', views.reject_record, name='record-reject'),
    path('records/<uuid:pk>/audit/', views.record_audit_trail, name='record-audit'),
    path('dashboard/', views.dashboard_stats, name='dashboard'),
    path('audit-log/', views.audit_log, name='audit-log'),
]
