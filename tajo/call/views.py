from django.shortcuts import render

# Create your views here.
from django.http import HttpResponse
from django.shortcuts import render

def call_home(request):
    return render(request, 'call/call_home.html')
