from django.urls import path
from . import views

urlpatterns = [
    path('', views.mypage_home, name='mypage_home'),  # mypage 홈화면 url
]