from django.shortcuts import render

# Create your views here.
from django.http import HttpResponse
from django.shortcuts import render

def mypage_home(request):
    return render(request, 'mypage/mypage_home.html')
