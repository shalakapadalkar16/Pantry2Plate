"""
Recipe book endpoints.

Addressed by recipe id throughout, not SavedRecipe id — the client always
has the recipe id already, and (user, recipe) is unique.
"""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.pagination import StandardResultsPagination

from .serializers import (
    SavedRecipeSerializer,
    SaveRecipeSerializer,
    UpdateNotesSerializer,
)
from .services import SavedRecipeService


class SavedRecipeListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """GET /api/v1/recipes/saved/ — the user's recipe book."""
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(
            SavedRecipeService.list_for(request.user), request, view=self
        )
        return paginator.get_paginated_response(
            SavedRecipeSerializer(page, many=True).data
        )

    def post(self, request):
        """POST /api/v1/recipes/saved/ — add a recipe to the book."""
        serializer = SaveRecipeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        saved = SavedRecipeService.save(
            user=request.user,
            recipe_id=serializer.validated_data["recipe_id"],
            notes=serializer.validated_data["notes"],
        )
        return Response(
            SavedRecipeSerializer(saved).data, status=status.HTTP_201_CREATED
        )


class SavedRecipeDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, recipe_id):
        """PATCH /api/v1/recipes/saved/{recipe_id}/ — edit notes."""
        serializer = UpdateNotesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        saved = SavedRecipeService.update_notes(
            user=request.user,
            recipe_id=recipe_id,
            notes=serializer.validated_data["notes"],
        )
        return Response(SavedRecipeSerializer(saved).data)

    def delete(self, request, recipe_id):
        """DELETE /api/v1/recipes/saved/{recipe_id}/ — remove from the book."""
        SavedRecipeService.remove(user=request.user, recipe_id=recipe_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class SavedRecipeIdsView(APIView):
    """
    GET /api/v1/recipes/saved/ids/

    Bare list of saved recipe ids so a client can mark search results
    without that flag entering the recommendation response — which is
    cached on a key that does not account for per-user state beyond the
    pantry. One small uncached call is cheaper than making the expensive
    cached one user-specific.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        ids = SavedRecipeService.saved_recipe_ids(request.user)
        return Response({"count": len(ids), "recipe_ids": ids})