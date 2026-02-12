from django.urls import path
from . import views

app_name = 'deadlines'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('matter/<int:pk>/', views.matter_detail, name='matter_detail'),
    path('matter/new/', views.matter_create, name='matter_create'),
    path('matter/<int:pk>/edit/', views.matter_edit, name='matter_edit'),
    path('matter/<int:matter_pk>/deadline/add/', views.deadline_add, name='deadline_add'),
    path('deadline/<int:pk>/edit/', views.deadline_edit, name='deadline_edit'),
    path('deadline/<int:pk>/complete/', views.deadline_complete, name='deadline_complete'),
    path('client/new/', views.client_create, name='client_create'),
    path('setup/', views.setup_admin, name='setup_admin'),
]
