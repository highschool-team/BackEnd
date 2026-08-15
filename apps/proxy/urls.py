from django.urls import re_path
from .views import OpenAIProxyView, AnthropicProxyView, GeminiProxyView

urlpatterns = [
    re_path(r'^openai/(?P<path>.*)$', OpenAIProxyView.as_view(), name='proxy-openai'),
    re_path(r'^anthropic/(?P<path>.*)$', AnthropicProxyView.as_view(), name='proxy-anthropic'),
    re_path(r'^gemini/(?P<path>.*)$', GeminiProxyView.as_view(), name='proxy-gemini'),
]
