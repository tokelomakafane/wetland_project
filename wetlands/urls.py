from django.urls import path

from . import views

app_name = 'wetlands'

urlpatterns = [
    path('wetlands/', views.wetland_registry, name='wetland_registry'),
    path('wetlands/add/', views.add_wetland, name='add_wetland'),
    path('wetlands/upload/', views.upload_wetlands, name='upload_wetlands'),
    path('wetlands/<int:pk>/edit/', views.edit_wetland, name='edit_wetland'),
    path('wetlands/<int:pk>/delete/', views.delete_wetland, name='delete_wetland'),
    path('wetlands/<int:pk>/monitor/', views.monitor_wetland, name='monitor_wetland'),
    path('api/wetlands/<int:pk>/erosion/', views.api_wetland_erosion_data, name='api_wetland_erosion'),
    path('api/wetlands/<int:pk>/health/', views.api_wetland_health_metrics, name='api_wetland_health'),
    path('api/wetlands/compare/', views.api_wetland_comparison, name='api_wetland_compare'),
    path('api/wetlands/<int:pk>/predict/', views.api_wetland_prediction, name='api_wetland_prediction'),
]
