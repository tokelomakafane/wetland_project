from django.urls import path
from . import views

app_name = 'mapping'

urlpatterns = [
    path('', views.index, name='index'),
    path('login/', views.login_view, name='login'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('monitor/', views.monitor_view, name='monitor'),
    path('lst/', views.lst_view, name='lst'),
    path('alerts/', views.alerts_view, name='alerts'),
    path('community/', views.community_view, name='community'),
    path('drone-upload/', views.drone_upload_view, name='drone_upload'),
    path('users/', views.users_view, name='users'),
    path('api/ee-tiles/', views.ee_tile_url, name='ee_tiles'),
    path('api/wetland-stats/', views.wetland_stats, name='wetland_stats'),
    path('api/sample-sites/', views.sample_sites, name='sample_sites'),
    path('api/lst-data/', views.wetland_lst, name='lst_data'),
    path('api/lst-predict/', views.wetland_lst_predict, name='lst_predict'),
    path('erosion/', views.erosion_view, name='erosion'),
    path('timelapse/', views.timelapse_view, name='timelapse'),
    path('api/erosion-data/', views.wetland_erosion, name='erosion_data'),
    path('api/erosion-compare/', views.wetland_erosion_compare, name='erosion_compare'),
    path('api/erosion-predict/', views.wetland_erosion_predict, name='erosion_predict'),
    
    # New Wetland Management Routes
    path('wetlands/', views.wetland_registry, name='wetland_registry'),
    path('wetlands/add/', views.add_wetland, name='add_wetland'),
    path('wetlands/upload/', views.upload_wetlands, name='upload_wetlands'),
    path('wetlands/<int:pk>/monitor/', views.monitor_wetland, name='monitor_wetland'),
    path('wetlands/<int:pk>/timelapse/', views.wetland_timelapse_view, name='wetland_timelapse'),
    path('api/wetlands/<int:pk>/erosion/', views.api_wetland_erosion_data, name='api_wetland_erosion'),
    path('api/wetlands/compare/', views.api_wetland_comparison, name='api_wetland_compare'),
    path('api/wetlands/<int:pk>/predict/', views.api_wetland_prediction, name='api_wetland_prediction'),
    path('api/timelapse/start/', views.api_timelapse_start, name='api_timelapse_start'),
    path('api/timelapse/<int:job_id>/status/', views.api_timelapse_status, name='api_timelapse_status'),
    path('api/timelapse/<int:job_id>/frames/', views.api_timelapse_frames, name='api_timelapse_frames'),
    path('api/timelapse/<int:job_id>/download/', views.api_timelapse_download, name='api_timelapse_download'),
]
