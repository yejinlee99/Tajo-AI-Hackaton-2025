from django.urls import path
from . import views

urlpatterns = [
    path('', views.guide_home, name='guide_home'),  # guide 홈화면 url
]