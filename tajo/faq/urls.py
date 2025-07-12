from django.urls import path
from . import views

urlpatterns = [
    path('', views.faq_home, name='faq_home'),  # faq 홈화면 url
]