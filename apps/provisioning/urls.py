from django.urls import path
from .views import (
    OnboardView,
    OffboardView,
    ProvisioningTaskDetailView,
    ProvisioningTaskStreamView,
)

urlpatterns = [
    path('onboard/', OnboardView.as_view(), name='provisioning-onboard'),
    path('offboard/', OffboardView.as_view(), name='provisioning-offboard'),
    path('tasks/<uuid:task_id>/', ProvisioningTaskDetailView.as_view(), name='provisioning-task-detail'),
    path('tasks/<uuid:task_id>/stream/', ProvisioningTaskStreamView.as_view(), name='provisioning-task-stream'),
]
