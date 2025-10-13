from django.urls import path
from . import views

app_name = 'viz'

urlpatterns = [
    path('', views.index, name='index'),
    path('api/histogram/<int:pk>/', views.get_histogram_data, name='histogram_data'),
    path('export/pdf/', views.export_pdf, name='export_pdf'),
]