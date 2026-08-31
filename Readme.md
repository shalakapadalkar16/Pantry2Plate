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
| Pantry CRUD with audit log | Working |
| Canonical ingredient vocabulary | Working — 136 ingredients, 419 aliases |
| Free-text ingredient matcher | Working — 30 tests passing |
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
across a corpus with hundreds of thousands of ingredient strings and the
matching problem *is* the product.

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

The alias table is loaded into memory once per process. During recipe import
the matcher is called on the order of a million times, and a database round
trip per lookup would dominate runtime.

---

## Known limitations

**Coverage is presence-based, not quantity-based.** The system asks whether
you have an ingredient, not whether you have enough. Comparing `2 cups flour`
against `500 g flour` requires per-ingredient density data that public recipe
datasets do not ship. Units are stored and normalised within a dimension
(g↔kg, tsp↔cup) but mass and volume are never interconverted. Adding a
density column to `Ingredient` is the extension path.

**The seed vocabulary is a starting point.** 136 hand-written ingredients will
not cover a large recipe corpus. The real vocabulary has to be mined from the
dataset itself and curated. Until then, match rate on real recipe text is
unmeasured.

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
├── ingredients/     canonical vocabulary, units, matcher
├── pantry/          pantry items and audit log
├── recipes/         scaffolded
├── recommendations/ scaffolded
├── data/            seed vocabulary
└── tests/
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

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/auth/register/` | Create an account |
| POST | `/api/v1/auth/login/` | Obtain JWT pair |
| GET/POST | `/api/v1/pantry/` | List or add pantry items |
| PATCH/DELETE | `/api/v1/pantry/{id}/` | Update or remove an item |
| GET | `/api/v1/pantry/logs/` | Audit trail |

---

## Licence

MIT.