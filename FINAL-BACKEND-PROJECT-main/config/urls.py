"""
URL configuration for the HubSpot Deals Extraction Service.
"""

from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    # Django admin (useful for inspecting data)
    path("admin/", admin.site.urls),

    # API v1 routes
    path("api/v1/", include("api.urls")),

    # OpenAPI schema + Swagger UI
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
]
