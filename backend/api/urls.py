from django.urls import path
from .views import HelloView, ChatbotView

urlpatterns = [
    path('hello/', HelloView.as_view(), name='hello'),
    path('chat/', ChatbotView.as_view(), name='chat'),
]