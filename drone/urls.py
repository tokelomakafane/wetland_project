from django.urls import path

from . import views

app_name = 'drone'

urlpatterns = [
    path('', views.drone_upload_view, name='drone_upload'),
    path('analyze/', views.api_drone_image_analysis, name='api_analysis'),
]
