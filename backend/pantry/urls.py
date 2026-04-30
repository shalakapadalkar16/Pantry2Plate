from django.urls import path

from .views import IngredientLogView, PantryDetailView, PantryListCreateView

urlpatterns = [
    path("", PantryListCreateView.as_view(), name="pantry-list-create"),
    path("<int:pk>/", PantryDetailView.as_view(), name="pantry-detail"),
    path("logs/", IngredientLogView.as_view(), name="pantry-logs"),
]