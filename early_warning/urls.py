from django.urls import path

from . import views

app_name = 'early_warning'

urlpatterns = [
    path('api/alerts/early-warning/', views.api_early_warning_alerts, name='alerts'),
]
