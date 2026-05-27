from django.urls import path
from . import views

urlpatterns = [
    path('sources/', views.DataSourceListCreateView.as_view(), name='sources-list'),
    path('batches/', views.ImportBatchListView.as_view(), name='batches-list'),
    path('batches/<uuid:batch_id>/', views.batch_detail, name='batch-detail'),
    path('upload/', views.upload_file, name='upload'),
]
