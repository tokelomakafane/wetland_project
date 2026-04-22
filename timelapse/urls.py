from django.urls import path

from . import views

app_name = 'timelapse'

urlpatterns = [
    path('timelapse/', views.timelapse_view, name='timelapse'),
    path('wetlands/<int:pk>/timelapse/', views.wetland_timelapse_view, name='wetland_timelapse'),
    path('api/timelapse/start/', views.api_timelapse_start, name='api_timelapse_start'),
    path('api/timelapse/<int:job_id>/status/', views.api_timelapse_status, name='api_timelapse_status'),
    path('api/timelapse/<int:job_id>/frames/', views.api_timelapse_frames, name='api_timelapse_frames'),
    path('api/timelapse/<int:job_id>/download/', views.api_timelapse_download, name='api_timelapse_download'),
]
