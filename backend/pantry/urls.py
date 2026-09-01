from django.urls import path

from .views import (
    ExpiringItemsView,
    IngredientLogView,
    PantryDetailView,
    PantryListCreateView,
)

urlpatterns = [
    path("", PantryListCreateView.as_view(), name="pantry-list-create"),
    # Literal paths before the pk pattern. <int:pk> will not match "logs"
    # today, but ordering that depends on the converter type is a trap.
    path("logs/", IngredientLogView.as_view(), name="pantry-logs"),
    path("expiring/", ExpiringItemsView.as_view(), name="pantry-expiring"),
    path("<int:pk>/", PantryDetailView.as_view(), name="pantry-detail"),
]
