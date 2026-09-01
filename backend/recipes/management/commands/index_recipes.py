"""
Build the Elasticsearch recipe index from Postgres.

Separate from import_recipes on purpose. Import parses 231k CSV rows and
runs once; reindexing happens every time the mapping or the vocabulary
changes. Merging them would mean re-parsing the whole corpus to fix a
field type.

    python manage.py index_recipes
    python manage.py index_recipes --recreate
"""

import time

from django.core.management.base import BaseCommand, CommandError

from recipes.models import Recipe, RecipeIngredient
from recipes.search import INDEX_NAME, MAPPING, build_document, get_client


class Command(BaseCommand):
    help = "Index recipes into Elasticsearch."

    def add_arguments(self, parser):
        parser.add_argument(
            "--recreate",
            action="store_true",
            help="Delete and rebuild the index. Required after a mapping change.",
        )
        parser.add_argument("--batch-size", type=int, default=2000)
        parser.add_argument("--limit", type=int, default=0)

    def handle(self, *args, **options):
        from elasticsearch import helpers

        client = get_client()
        if not client.ping():
            raise CommandError(
                "Elasticsearch is not reachable. Try: docker compose up -d elasticsearch"
            )

        if options["recreate"] and client.indices.exists(index=INDEX_NAME):
            client.indices.delete(index=INDEX_NAME)
            self.stdout.write("Deleted existing index.")

        if not client.indices.exists(index=INDEX_NAME):
            client.indices.create(index=INDEX_NAME, **MAPPING)
            self.stdout.write(f"Created index '{INDEX_NAME}'.")

        # Disable refresh during the bulk load. Refreshing after every batch
        # forces segment creation and roughly doubles indexing time for an
        # index nobody is querying yet.
        client.indices.put_settings(index=INDEX_NAME, settings={"refresh_interval": "-1"})

        started = time.perf_counter()
        indexed = 0
        errors = 0

        try:
            for ok, info in helpers.streaming_bulk(
                client,
                self._documents(options["batch_size"], options["limit"]),
                chunk_size=1000,
                max_retries=3,
                raise_on_error=False,
            ):
                if ok:
                    indexed += 1
                    if indexed % 10_000 == 0:
                        self.stdout.write(f"  {indexed:,} indexed", ending="\r")
                        self.stdout.flush()
                else:
                    errors += 1
                    if errors <= 3:
                        self.stderr.write(f"\n{info}")
        finally:
            # Restore refresh even if indexing failed, or the index stays
            # permanently stale and queries silently return nothing new.
            client.indices.put_settings(
                index=INDEX_NAME, settings={"refresh_interval": "1s"}
            )
            client.indices.refresh(index=INDEX_NAME)

        elapsed = time.perf_counter() - started
        count = client.count(index=INDEX_NAME)["count"]

        self.stdout.write(f"\n\n{'=' * 54}")
        self.stdout.write("INDEX")
        self.stdout.write(f"{'=' * 54}")
        self.stdout.write(f"  indexed        {indexed:,}")
        self.stdout.write(f"  errors         {errors:,}")
        self.stdout.write(f"  docs in index  {count:,}")
        self.stdout.write(f"  elapsed        {elapsed:.1f}s")
        if elapsed:
            self.stdout.write(f"  rate           {indexed / elapsed:,.0f} docs/s")

    # ---------------------------------------------------------- generator

    def _documents(self, batch_size: int, limit: int):
        """
        Stream documents, batching the ingredient lookup.

        Fetching ingredient ids per recipe would be 231k queries. Instead
        recipes come in batches and their ingredient rows are fetched in one
        query per batch, then grouped in memory — about 230 queries total.
        """
        fields = (
            "id", "external_id", "name", "minutes", "tags",
            "calories", "n_ingredients", "n_required", "n_unresolved",
        )

        queryset = Recipe.objects.order_by("id").values(*fields)
        if limit:
            queryset = queryset[:limit]

        batch: list[dict] = []
        for row in queryset.iterator(chunk_size=batch_size):
            batch.append(row)
            if len(batch) >= batch_size:
                yield from self._batch_to_docs(batch)
                batch = []

        if batch:
            yield from self._batch_to_docs(batch)

    @staticmethod
    def _batch_to_docs(batch: list[dict]):
        recipe_ids = [row["id"] for row in batch]

        # Only non-staple resolved ingredients go into the document.
        # Staples are assumed present and excluded from n_required;
        # unresolved rows have no id and must never be matchable.
        by_recipe: dict[int, list[int]] = {rid: [] for rid in recipe_ids}
        pairs = RecipeIngredient.objects.filter(
            recipe_id__in=recipe_ids,
            is_staple=False,
            ingredient_id__isnull=False,
        ).values_list("recipe_id", "ingredient_id")

        for recipe_id, ingredient_id in pairs:
            by_recipe[recipe_id].append(ingredient_id)

        for row in batch:
            yield {
                "_index": INDEX_NAME,
                "_id": row["id"],
                "_source": build_document(row, by_recipe[row["id"]]),
            }