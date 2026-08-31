"""
Pantry endpoints.

These are thin on purpose: validate input, call the service, serialize the
result. Error handling is gone from the views entirely — services raise
typed exceptions and core.exceptions.custom_exception_handler turns them
into responses. That removes the two competing error formats the codebase
previously had.
"""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.pagination import StandardResultsPagination

from .serializers import (
    IngredientLogSerializer,
    PantryItemCreateSerializer,
    PantryItemSerializer,
    PantryItemUpdateSerializer,
)
from .services import PantryService


class PaginatedListMixin:
    """
    APIView does not honour DEFAULT_PAGINATION_CLASS — only generics and
    viewsets do. The setting was configured but inert, so both list
    endpoints returned every row.
    """

    pagination_class = StandardResultsPagination

    def paginated_response(self, request, queryset, serializer_class):
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(serializer_class(page, many=True).data)


class PantryListCreateView(PaginatedListMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """GET /api/v1/pantry/ — list the user's pantry."""
        return self.paginated_response(
            request, PantryService.get_pantry(request.user), PantryItemSerializer
        )

    def post(self, request):
        """POST /api/v1/pantry/ — add an ingredient."""
        serializer = PantryItemCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        item = PantryService.add_item(user=request.user, **serializer.validated_data)
        return Response(
            PantryItemSerializer(item).data, status=status.HTTP_201_CREATED
        )


class PantryDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        """PATCH /api/v1/pantry/{id}/ — partial update."""
        serializer = PantryItemUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        data = dict(serializer.validated_data)
        # An explicit null clears the date; an absent key leaves it alone.
        # Without this distinction PATCH cannot remove an expiry.
        clear_expiry = "expiry_date" in data and data["expiry_date"] is None
        data.pop("expiry_date", None) if clear_expiry else None

        item = PantryService.update_item(
            user=request.user, item_id=pk, clear_expiry=clear_expiry, **data
        )
        return Response(PantryItemSerializer(item).data)

    def delete(self, request, pk):
        """DELETE /api/v1/pantry/{id}/ — remove an ingredient."""
        PantryService.remove_item(user=request.user, item_id=pk)
        return Response(status=status.HTTP_204_NO_CONTENT)


class IngredientLogView(PaginatedListMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """GET /api/v1/pantry/logs/ — paginated audit trail."""
        return self.paginated_response(
            request, PantryService.get_logs(request.user), IngredientLogSerializer
        )


class ExpiringItemsView(PaginatedListMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """GET /api/v1/pantry/expiring/?days=7 — items approaching expiry."""
        try:
            days = int(request.query_params.get("days", 7))
        except ValueError:
            days = 7
        days = max(0, min(days, 365))

        return self.paginated_response(
            request,
            PantryService.get_expiring(request.user, within_days=days),
            PantryItemSerializer,
        )