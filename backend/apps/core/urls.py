from django.urls import path
from . import views

urlpatterns = [
    path('me/', views.me, name='me'),
    path('setup/', views.setup, name='setup'),
]
