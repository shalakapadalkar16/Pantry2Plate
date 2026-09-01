# Pantry2Plate

Find recipes you can actually cook with what is in your kitchen right now.

Enter what you have, pick a mood, and get recipes ranked by how much of the
ingredient list you already own — either strictly what you have, or with a
short shopping list if you are willing to buy a few things.

---

## Status

Under active development. Honest breakdown of what exists:

| Area | State |
|---|---|
| User accounts, JWT auth | Working |
| Pantry CRUD, audit log, expiry tracking | Working — 25 API tests |
| Canonical ingredient vocabulary | Working — 136 ingredients, 419 aliases |
| Free-text ingredient matcher | Working — 30 tests, measured against 2.1M real strings |
| Compound ingredient splitting | Next up |
| Recipe corpus and import | Not started |
| Coverage scoring and ranking | Not started |
| Elasticsearch retrieval | Container runs; nothing indexed yet |
| Redis caching | Configured; nothing cached yet |
| Mood filtering | Not started |
| Saved recipe book | Not started |

---

## Why the ingredient layer exists

The obvious version of this app stores pantry items as free text and compares
them to recipe ingredient strings. That does not work.

A user types `olive oil`. A recipe says `2 tbsp extra virgin olive oil`. Those
are the same thing and no string comparison will tell you so. Multiply that
across a corpus with two million ingredient strings and the matching problem
*is* the product.

So both pantry items and recipe ingredients point at a shared `Ingredient`
table. Once identifiers line up on both sides, coverage becomes a set
operation instead of a text problem:

```
have     = recipe ingredients present in the pantry, or flagged as staples
missing  = required − have
coverage = have / required
```

Pantry-only mode is `missing == 0`. Shopping mode is `missing <= k`.
Two modes, one query, one parameter.

### Resolving free text

`ingredients/matcher.py` turns a raw string into an `Ingredient` using a
ladder. Each rung discards more information than the one above it, and the
first exact hit wins:

| Rung | Example |
|---|---|
| Exact name or alias | `EVOO` → Olive Oil |
| Strip quantities and measures | `1 lb ground beef` → Ground Beef |
| Strip preparation words | `2 finely chopped fresh basil leaves` → Basil |
| Fuzzy, strict threshold | `corriander` → Coriander Leaves |

Stripping only ever runs after exact lookup fails. That ordering matters:
`ground` looks like a preparation word, but `ground beef` and `ground cumin`
are identities. Trying the least destructive interpretation first is what
makes aggressive stripping safe further down.

Fuzzy matching is deliberately last and deliberately strict. A wrong match
tells a user they can cook something they cannot, which is worse than
admitting a miss. Anything that fails every rung is recorded in
`UnmatchedIngredient` with a hit counter, so vocabulary gaps are measurable
rather than invisible.

The alias table is loaded into memory once per process. Importing the corpus
calls the matcher two million times, and a database round trip per lookup
would dominate runtime.

---

## Measured coverage

`python manage.py mine_vocabulary` runs the matcher across the full Food.com
corpus and reports how much of real recipe text it resolves.

**231,637 recipes · 2,096,582 ingredient mentions · 14,942 distinct strings**

| Metric | Result |
|---|---|
| Coverage by occurrence | **69.3%** |
| Coverage by distinct string | 9.0% |

The occurrence figure is the one that matters. Distinct-string coverage falls
as the corpus grows, because the long tail grows faster than the head —
optimising it means curating one-offs like `ancho chile powder` that almost
nobody has.

Ingredient frequency is heavily skewed, which sets the curation budget:

| Distinct strings curated | Share of all mentions |
|---|---|
| 89 | 50% |
| 615 | 80% |
| 1,449 | 90% |
| 6,606 | 99% |

Past roughly 1,500 entries the trade stops being worth it.

Which rung does the work, by occurrence: exact 94.1%, descriptors 4.1%, fuzzy
1.2%, measures 0.6%. Fuzzy contributes almost nothing here because the corpus
is machine-cleaned. It earns its place on the pantry side, where a human types
`corriander`. The same matcher serves two input distributions with different
error profiles.

---

## Known limitations

**Compound strings are the largest single gap.** `salt and pepper` appears
15,415 times and cannot resolve, because the matcher assumes one string maps
to one ingredient. This is an architectural gap, not a missing alias — no
amount of vocabulary fixes it.

**Coverage is presence-based, not quantity-based.** The system asks whether
you have an ingredient, not whether you have enough. Comparing `2 cups flour`
against `500 g flour` requires per-ingredient density data that public recipe
datasets do not ship. Units are stored and normalised within a dimension
(g↔kg, tsp↔cup) but mass and volume are never interconverted. Adding a
density column to `Ingredient` is the extension path.

**Some strings are genuinely ambiguous.** `oil` (9,925 mentions), `cheese`
(2,712) and `nuts` (2,421) name a category, not an ingredient. These need a
product decision about generic ingredients, not a lookup.

---

## Stack

- **Backend** — Django 5 + DRF, service-layer architecture, split settings
- **Frontend** — React + TypeScript + Vite, Zustand for auth state
- **Data** — PostgreSQL 16
- **Planned** — Elasticsearch for recipe retrieval, Redis for recommendation caching

## Layout

```
backend/
├── config/          settings (base/dev/prod), root urls
├── core/            shared base models, pagination, exception handling
├── users/           custom user model, JWT auth
├── ingredients/     canonical vocabulary, units, matcher, corpus mining
├── pantry/          pantry items and audit log
├── recipes/         scaffolded
├── recommendations/ scaffolded
├── data/            seed vocabulary, coverage report (raw corpus gitignored)
└── tests/           55 tests
```

## Running it

```bash
cp .env.example .env          # fill in the values
docker compose up -d          # postgres, redis, elasticsearch
python manage.py migrate
python manage.py load_ingredients
python manage.py runserver
```

Tests:

```bash
pytest
```

Coverage measurement (needs `RAW_recipes.csv` from the Food.com Kaggle
dataset at `data/raw/`):

```bash
python manage.py mine_vocabulary
```

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/auth/register/` | Create an account |
| POST | `/api/v1/auth/login/` | Obtain JWT pair |
| GET/POST | `/api/v1/pantry/` | List or add pantry items |
| PATCH/DELETE | `/api/v1/pantry/{id}/` | Update or remove an item |
| GET | `/api/v1/pantry/logs/` | Audit trail |
| GET | `/api/v1/pantry/expiring/?days=7` | Items approaching expiry |

All list endpoints are paginated. Errors share one shape:

```json
{"error": {"message": "...", "code": "...", "status_code": 400, "fields": {}}}
```

---

## Licence

MIT.