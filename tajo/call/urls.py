from django.urls import path
from . import views

urlpatterns = [
    path('', views.call_home, name='call_home'),  # call 홈화면 url
]