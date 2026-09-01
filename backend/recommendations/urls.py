from django.urls import path

from .views import MoodCatalogView, RecipeDetailView, RecommendationView

urlpatterns = [
    path("", RecommendationView.as_view(), name="recommendations"),
    # Literal segments before any pk pattern, as in pantry/urls.py.
    path("moods/", MoodCatalogView.as_view(), name="moods"),
    path("recipes/<int:pk>/", RecipeDetailView.as_view(), name="recipe-detail"),
]
