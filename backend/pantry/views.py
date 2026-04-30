from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import (
    IngredientLogSerializer,
    PantryItemCreateSerializer,
    PantryItemSerializer,
    PantryItemUpdateSerializer,
)
from .services import PantryService


class PantryListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """GET /api/v1/pantry/ — list all pantry items for the logged in user."""
        items = PantryService.get_pantry(request.user)
        serializer = PantryItemSerializer(items, many=True)
        return Response(serializer.data)

    def post(self, request):
        """POST /api/v1/pantry/ — add a new ingredient."""
        serializer = PantryItemCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            item = PantryService.add_item(
                user=request.user,
                ingredient_name=serializer.validated_data["ingredient_name"],
                quantity=serializer.validated_data["quantity"],
                unit=serializer.validated_data["unit"],
            )
        except ValueError as e:
            return Response(
                {"error": {"message": str(e), "status_code": 400}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(PantryItemSerializer(item).data, status=status.HTTP_201_CREATED)


class PantryDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        """PATCH /api/v1/pantry/{id}/ — update quantity and unit."""
        serializer = PantryItemUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            item = PantryService.update_item(
                user=request.user,
                item_id=pk,
                quantity=serializer.validated_data["quantity"],
                unit=serializer.validated_data["unit"],
            )
        except ValueError as e:
            return Response(
                {"error": {"message": str(e), "status_code": 404}},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(PantryItemSerializer(item).data)

    def delete(self, request, pk):
        """DELETE /api/v1/pantry/{id}/ — remove an ingredient."""
        try:
            PantryService.remove_item(user=request.user, item_id=pk)
        except ValueError as e:
            return Response(
                {"error": {"message": str(e), "status_code": 404}},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(status=status.HTTP_204_NO_CONTENT)


class IngredientLogView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """GET /api/v1/pantry/logs/ — return full audit log for the user."""
        logs = PantryService.get_logs(request.user)
        serializer = IngredientLogSerializer(logs, many=True)
        return Response(serializer.data)