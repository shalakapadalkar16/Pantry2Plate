from django.urls import path

from .views import RecipeDetailView, RecommendationView

urlpatterns = [
    path("", RecommendationView.as_view(), name="recommendations"),
    # Literal segments before the pk pattern, as in pantry/urls.py.
    path("recipes/<int:pk>/", RecipeDetailView.as_view(), name="recipe-detail"),
]