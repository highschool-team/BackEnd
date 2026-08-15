from django.urls import path
from .views import (
    TeamListView,
    TeamDetailView,
    TeamBudgetView,
    TeamProviderListView,
    TeamProviderDetailView,
    TeamProviderLimitView,
    TeamProviderModelView,
    TeamIPAllowlistView,
    TeamIPAllowlistDetailView,
    TeamProviderRateLimitView,
    TeamProviderUnsuspendView,
)
from apps.usage.views import TeamUsageView, TeamMembersUsageView

urlpatterns = [
    path('', TeamListView.as_view(), name='team-list'),
    path('<uuid:pk>/', TeamDetailView.as_view(), name='team-detail'),
    path('<uuid:pk>/budget/', TeamBudgetView.as_view(), name='team-budget'),
    path('<uuid:pk>/providers/', TeamProviderListView.as_view(), name='team-provider-list'),
    path('<uuid:pk>/providers/<str:provider_name>/', TeamProviderDetailView.as_view(), name='team-provider-detail'),
    path('<uuid:pk>/providers/<str:provider_name>/limit/', TeamProviderLimitView.as_view(), name='team-provider-limit'),
    path('<uuid:pk>/providers/<str:provider_name>/model/', TeamProviderModelView.as_view(), name='team-provider-model'),
    path('<uuid:pk>/providers/<str:provider_name>/rate-limit/', TeamProviderRateLimitView.as_view(), name='team-provider-rate-limit'),
    path('<uuid:pk>/providers/<str:provider_name>/unsuspend/', TeamProviderUnsuspendView.as_view(), name='team-provider-unsuspend'),
    path('<uuid:pk>/ip-allowlist/', TeamIPAllowlistView.as_view(), name='team-ip-allowlist'),
    path('<uuid:pk>/ip-allowlist/<uuid:entry_id>/', TeamIPAllowlistDetailView.as_view(), name='team-ip-allowlist-detail'),
    path('<uuid:pk>/usage/', TeamUsageView.as_view(), name='team-usage'),
    path('<uuid:pk>/members/usage/', TeamMembersUsageView.as_view(), name='team-members-usage'),
]
