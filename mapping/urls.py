from django.urls import path
from . import views

app_name = 'mapping'

urlpatterns = [
    path('', views.index, name='index'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('monitor/', views.monitor_view, name='monitor'),
    path('lst/', views.lst_view, name='lst'),
    path('alerts/', views.alerts_view, name='alerts'),
    path('community/', views.community_view, name='community'),
    path('api/community-inputs/', views.api_list_community_inputs, name='community_input_list'),
    path('api/community-inputs/create/', views.api_create_community_input, name='community_input_create'),
    path('api/community-inputs/<int:input_id>/', views.api_get_community_input, name='community_input_detail'),
    path('api/community-inputs/<int:input_id>/update/', views.api_update_community_input, name='community_input_update'),
    path('api/community-inputs/<int:input_id>/delete/', views.api_delete_community_input, name='community_input_delete'),
    path('users/', views.users_view, name='users'),
    path('api/alerts/early-warning/', views.api_early_warning_alerts, name='early_warning_alerts'),
    path('api/alerts/early-warning/read/', views.api_mark_early_warning_alert_read, name='mark_early_warning_alert_read'),
    path('api/ee-tiles/', views.ee_tile_url, name='ee_tiles'),
    path('api/wetland-stats/', views.wetland_stats, name='wetland_stats'),
    path('api/sample-sites/', views.sample_sites, name='sample_sites'),
    path('api/lst-data/', views.wetland_lst, name='lst_data'),
    path('api/lst-predict/', views.wetland_lst_predict, name='lst_predict'),
    path('erosion/', views.erosion_view, name='erosion'),
    path('api/erosion-data/', views.wetland_erosion, name='erosion_data'),
    path('api/erosion-compare/', views.wetland_erosion_compare, name='erosion_compare'),
    path('api/erosion-predict/', views.wetland_erosion_predict, name='erosion_predict'),
]
