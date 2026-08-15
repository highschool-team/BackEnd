from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

urlpatterns = [
    path('admin/', admin.site.urls),

    # Swagger
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('swagger', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    path('api/auth/', include('apps.authentication.urls')),
    path('api/teams/', include('apps.teams.urls')),
    path('api/proxy/', include('apps.proxy.urls')),
    path('api/dashboard/', include('apps.usage.urls')),
    path('api/alerts/', include('apps.alerts.urls')),
    path('api/provisioning/', include('apps.provisioning.urls')),
]
