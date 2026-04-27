from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/auth/", include("users.urls")),
    path("api/v1/pantry/", include("pantry.urls")),
    path("api/v1/recipes/", include("recipes.urls")),
    path("api/v1/recommendations/", include("recommendations.urls")),
]
