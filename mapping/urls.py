from django.urls import path
from . import views

app_name = 'mapping'

urlpatterns = [
    path('', views.index, name='index'),
    path('login/', views.login_view, name='login'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('monitor/', views.monitor_view, name='monitor'),
    path('alerts/', views.alerts_view, name='alerts'),
    path('community/', views.community_view, name='community'),
    path('drone-upload/', views.drone_upload_view, name='drone_upload'),
    path('users/', views.users_view, name='users'),
    path('api/ee-tiles/', views.ee_tile_url, name='ee_tiles'),
    path('api/wetland-stats/', views.wetland_stats, name='wetland_stats'),
    path('api/sample-sites/', views.sample_sites, name='sample_sites'),
]
