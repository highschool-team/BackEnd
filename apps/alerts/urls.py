from django.urls import path
from .views import AlertListView, AlertReadView, AlertStreamView

urlpatterns = [
    path('', AlertListView.as_view(), name='alert-list'),
    path('stream/', AlertStreamView.as_view(), name='alert-stream'),
    path('<uuid:pk>/read/', AlertReadView.as_view(), name='alert-read'),
]
