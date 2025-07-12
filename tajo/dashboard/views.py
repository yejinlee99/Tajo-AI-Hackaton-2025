from django.shortcuts import render

# Create your views here.
from django.http import HttpResponse
from django.shortcuts import render

def dashboard_home(request):
    return render(request, 'dashboard/dashboard_home.html')
