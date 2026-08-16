from django.urls import path
from .views import LoginView, RefreshView, LogoutView, VirtualAPIKeyView, VirtualAPIKeyDetailView

urlpatterns = [
    path('login/', LoginView.as_view(), name='auth-login'),
    path('refresh/', RefreshView.as_view(), name='auth-refresh'),
    path('logout/', LogoutView.as_view(), name='auth-logout'),
    path('api-keys/', VirtualAPIKeyView.as_view(), name='auth-api-keys'),
    path('api-keys/<uuid:pk>/', VirtualAPIKeyDetailView.as_view(), name='auth-api-keys-detail'),
]
