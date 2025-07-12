from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='main_home'),  # 메인 홈화면 url
]