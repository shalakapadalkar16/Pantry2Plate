"""
Recommendation endpoints.

Thin, as with pantry: validate, delegate to a service, serialize.

Two things happen here beyond that:

  * Backend selection. Elasticsearch is used when reachable and the SQL
    implementation is the fallback. Both return the same SearchResult, and
    the comparison command shows they agree, so falling back degrades
    latency rather than correctness.
  * Caching. The fully serialised payload is cached, not the SearchResult.
    On a hit there is no database access, no Elasticsearch call, and no
    serialisation — which is most of the work.

Pagination is assembled by hand rather than through DRF's paginator. The
service returns a dataclass, not a queryset, because the ranking is
computed in SQL and Painless that the ORM cannot express. The response
shape still matches the rest of the API so clients need no special case.
"""

from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import cache, moods
from .es_service import ElasticCoverageSearch
from .serializers import RecipeMatchSerializer, RecommendationQuerySerializer
from .services import CoverageSearch


class MoodCatalogView(APIView):
    """
    GET /api/v1/recommendations/moods/

    Public: the client needs this to render filter options before login,
    and it exposes nothing about anyone's data.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"moods": moods.catalog()})


class RecommendationView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        GET /api/v1/recommendations/

        Query params:
          max_missing   how many ingredients you are willing to buy (default 0)
          min_required  ignore recipes with fewer required ingredients (default 3)
          max_minutes   cook time ceiling
          mood          comma-separated mood keys, AND-ed together
          order         best | quickest | simplest
          limit, offset
          backend       sql | es  (override, for benchmarking)
        """
        query = RecommendationQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = dict(query.validated_data)

        limit = params.pop("limit")
        offset = params.pop("offset")
        mood_keys = params.pop("mood", [])
        backend_override = params.pop("backend", None)

        pantry_ids = CoverageSearch.pantry_ingredient_ids(request.user)

        # An empty pantry is not an error, but it is worth distinguishing
        # from "we searched and found nothing" — the client should prompt
        # the user to add ingredients rather than loosen filters.
        if not pantry_ids:
            return Response(
                {
                    "count": 0,
                    "next": None,
                    "previous": None,
                    "pantry_size": 0,
                    "moods_applied": [],
                    "results": [],
                    "detail": "Add ingredients to your pantry to get recommendations.",
                }
            )

        cache_params = {
            **params,
            "limit": limit,
            "offset": offset,
            "mood": mood_keys,
            "backend": backend_override,
        }
        cache_key = cache.build_key(request.user.pk, pantry_ids, cache_params)

        cached = cache.get(cache_key)
        if cached is not None:
            # Reported so the effect is observable rather than asserted.
            return Response({**cached, "cached": True})

        backend, backend_name = self._select_backend(backend_override)

        result = backend.search(
            pantry_ids,
            limit=limit,
            offset=offset,
            tag_groups=moods.resolve(mood_keys),
            **params,
        )

        payload = {
            "count": result.total,
            "next": self._page_url(request, offset + limit, limit, result.total),
            "previous": (
                self._page_url(request, max(offset - limit, 0), limit, result.total)
                if offset > 0
                else None
            ),
            "pantry_size": len(pantry_ids),
            # Echoed back so the client can show active filters without
            # re-parsing the query string.
            "moods_applied": mood_keys,
            "backend": backend_name,
            "results": RecipeMatchSerializer(result.matches, many=True).data,
        }

        cache.set(cache_key, payload)
        return Response({**payload, "cached": False})

    @staticmethod
    def _select_backend(override):
        """
        Elasticsearch when available, SQL otherwise.

        The availability check is a ping, so a dead cluster costs one failed
        connection rather than a 500. The comparison command establishes
        that both backends return the same results, which is what makes an
        automatic fallback safe.
        """
        if override == "sql":
            return CoverageSearch, "sql"
        if override == "es":
            return ElasticCoverageSearch, "es"
        if ElasticCoverageSearch.available():
            return ElasticCoverageSearch, "es"
        return CoverageSearch, "sql"

    @staticmethod
    def _page_url(request, new_offset, limit, total):
        if new_offset >= total:
            return None
        params = request.query_params.copy()
        params["offset"] = new_offset
        params["limit"] = limit
        return f"{request.build_absolute_uri(request.path)}?{params.urlencode()}"


class RecipeDetailView(APIView):
    """Full recipe, including steps and a per-ingredient have/missing view."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        from core.exceptions import ResourceNotFoundError
        from recipes.models import Recipe

        try:
            recipe = Recipe.objects.prefetch_related(
                "recipe_ingredients__ingredient"
            ).get(pk=pk)
        except Recipe.DoesNotExist:
            raise ResourceNotFoundError("Recipe not found.") from None

        pantry = set(CoverageSearch.pantry_ingredient_ids(request.user))

        ingredients = []
        for row in recipe.recipe_ingredients.all():
            if row.ingredient_id is None:
                state = "unknown"
            elif row.is_staple:
                state = "staple"
            elif row.ingredient_id in pantry:
                state = "have"
            else:
                state = "missing"

            ingredients.append(
                {
                    "raw_text": row.raw_text,
                    "display_name": (
                        row.ingredient.display_name if row.ingredient else row.raw_text
                    ),
                    "state": state,
                }
            )

        return Response(
            {
                "id": recipe.pk,
                "name": recipe.name,
                "description": recipe.description,
                "minutes": recipe.minutes,
                "tags": recipe.tags,
                "calories": recipe.calories,
                "nutrition": recipe.nutrition,
                "steps": recipe.steps,
                "ingredients": ingredients,
                # Staples are reported but never counted as missing, so the
                # client can explain why a recipe listing salt still shows
                # as fully covered.
                "summary": {
                    "n_required": recipe.n_required,
                    "have": sum(1 for i in ingredients if i["state"] == "have"),
                    "missing": sum(1 for i in ingredients if i["state"] == "missing"),
                    "unknown": sum(1 for i in ingredients if i["state"] == "unknown"),
                },
            }
        )