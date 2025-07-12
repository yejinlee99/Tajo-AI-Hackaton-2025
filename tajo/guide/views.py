from django.shortcuts import render

# Create your views here.
from django.http import HttpResponse
from django.shortcuts import render

def guide_home(request):
    return render(request, 'guide/guide_home.html')
