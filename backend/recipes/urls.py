from django.urls import path

from .views import SavedRecipeDetailView, SavedRecipeIdsView, SavedRecipeListView

urlpatterns = [
    # Literal segments before any pk pattern, as elsewhere in the project.
    path("saved/ids/", SavedRecipeIdsView.as_view(), name="saved-recipe-ids"),
    path("saved/", SavedRecipeListView.as_view(), name="saved-recipes"),
    path(
        "saved/<int:recipe_id>/",
        SavedRecipeDetailView.as_view(),
        name="saved-recipe-detail",
    ),
]
