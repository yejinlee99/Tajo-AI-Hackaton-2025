from django.shortcuts import render

# Create your views here.
from django.http import HttpResponse
from django.shortcuts import render

def faq_home(request):
    return render(request, 'faq/faq_home.html')
