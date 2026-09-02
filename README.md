# Pantry2Plate

Find recipes you can actually cook with what is in your kitchen right now.

It is 7pm. You have chicken, rice, half an onion and no intention of going
to the shop. Pantry2Plate ranks 231,637 recipes by how many ingredients you
are missing, so the things you can cook tonight are at the top.

---

## Status

Complete and measured. Runs locally; not publicly deployed.

| Area | State |
|---|---|
| Accounts, JWT auth, password validation, throttling | Working |
| Pantry CRUD, audit log, expiry tracking | Working |
| Ingredient vocabulary and matcher | Working — 87% corpus coverage |
| Recipe corpus | 231,637 recipes, 2.09M ingredient rows |
| Coverage ranking and search API | Working |
| Mood filtering | Working — 23 moods |
| Elasticsearch retrieval | Working — 5x faster than SQL, verified equivalent |
| Redis caching | Working — 105ms to 1.5ms |
| Saved recipe book | Working |
| React frontend | Working — pantry, search, recipe detail, recipe book |
| Containerized stack | Working — `docker compose up` runs everything |
| Tests | 120 |
| Public deployment | Not deployed, deliberately — see below |

---

## The interesting problem

The obvious build stores pantry items as free text and compares them to
recipe ingredient strings. That does not work.

A user types `olive oil`. A recipe says `2 tbsp extra virgin olive oil`.
Those are the same thing and no string comparison will say so. Across
2.1 million ingredient mentions, **the matching problem is the product** —
search, ranking, mood and caching all sit on top of it and are worthless
without it.

So both `PantryItem` and `RecipeIngredient` point at a shared `Ingredient`
table. Once identifiers line up, coverage stops being a text problem and
becomes a set operation:

```
n_required = non-staple ingredient rows on the recipe
have       = non-staple rows whose ingredient is in the pantry
missing    = n_required - have
```

Results are one ranked list sorted by `missing`, with a threshold the user
controls. "Only what I have" is that threshold at zero, not a separate mode.

### Resolving free text

`ingredients/matcher.py` resolves a string through a ladder. Each rung
discards more information than the one above it, and the first exact hit
wins:

| Rung | Example |
|---|---|
| Exact name or alias | `EVOO` → Olive Oil |
| Strip quantities and measures | `1 lb ground beef` → Ground Beef |
| Strip preparation words | `2 finely chopped fresh basil leaves` → Basil |
| Split compounds | `salt and pepper` → Salt + Black Pepper |
| Fuzzy, strict threshold | `corriander` → Coriander Leaves |

**The ordering is the design.** Stripping only runs after exact lookup
fails, which is what makes aggressive stripping safe: `dry mustard` and
`sweet potato` are vocabulary entries and never reach the stage where `dry`
and `sweet` would be removed. Splitting only runs after that, which is what
protects `cream of mushroom soup` and `pork and beans`.

Fuzzy matching is last and strict. A wrong match tells a user they can cook
something they cannot, which is worse than admitting a miss. Anything that
fails every rung is recorded in `UnmatchedIngredient` with a hit count, so
vocabulary gaps are measurable rather than invisible. Unresolved pantry
items are shown with a badge rather than hidden, because an unmatched item
will never appear in a result and the user should be able to see why.

### Three rules that decide what you see

**Staples are excluded from the denominator.** Nobody lists salt in their
pantry but nearly every recipe needs it. Counting staples would make every
recipe read as less cookable than it is. The recipe detail page shows them
in their own section so this is visible rather than mysterious.

**Unresolved ingredients always count as missing.** They have no id, so
nothing in a pantry can satisfy them. That is correct — the user cannot
confirm having something the matcher could not name.

**Ranking is by absolute overlap, not coverage ratio.** Once `missing` is 0
every recipe has coverage exactly 1.0, so the ratio carries no information.
Ranking by it returned two-ingredient recipes. A recipe using eight things
from your pantry is a better answer than one using two.

---

## Measured results

### Matcher coverage

`python manage.py mine_vocabulary` runs the matcher across the full corpus.

**231,637 recipes · 2,096,582 ingredient mentions · 14,942 distinct strings**

| Stage | Coverage by occurrence |
|---|---|
| Initial 136-ingredient vocabulary | 69.3% |
| + compound splitting, stricter fuzzy | 70.1% |
| + 152 curated ingredients | 83.3% |
| + alias pass (294 total) | **86.5%** |

Distinct-string coverage sits near 9% and *falls* as the corpus grows,
because the long tail grows faster than the head. Occurrence-weighted
coverage is what a user experiences.

Curation stopped at 294 entries because ingredient frequency is heavily
skewed:

| Distinct strings curated | Share of all mentions |
|---|---|
| 89 | 50% |
| 615 | 80% |
| 1,449 | 90% |
| 6,606 | 99% |

Past ~1,500 each entry buys about 0.03%.

### Recipe resolvability

| Unresolved ingredients | Recipes | Share |
|---|---|---|
| 0 | 72,173 | 31.2% |
| 1 | 79,541 | 34.3% |
| 2 | 47,995 | 20.7% |
| 3+ | 31,928 | 13.8% |

31.2% is the pool for a zero-missing search. The rest still work when the
user is willing to buy something. This distribution was measured *before*
the recipe schema was written — it is what made `n_unresolved` a real
column rather than a diagnostic afterthought.

### Search latency

Median of five runs, `limit=20`.

| Pantry size | Postgres | Elasticsearch | Speedup |
|---|---|---|---|
| 5 | 114ms | 10ms | 11.0x |
| 15 | 166ms | 29ms | 5.7x |
| 30 | 192ms | 37ms | 5.2x |

`python manage.py compare_search` produces this table and also verifies the
two backends agree: identical totals on all nine cases, 18–20/20 top-page
overlap, identical have/missing arithmetic. Remaining gaps are genuine ties.

With Redis warm, a repeat query is **1.5ms**.

### Import

231,637 recipes and 2,090,328 ingredient rows in **108 seconds**.
Elasticsearch index built in **8.9 seconds** at 26k docs/s.

---

## Architecture notes

**Elasticsearch uses `terms_set`.** A `minimum_should_match_script`
computes the threshold per document — `n_required - max_missing` — which
expresses the coverage rule directly. Without it this needs one query per
possible `n_required` value or a script filter over the whole index.

**Ranking is packed into one score:** `(20 - missing) * 1000 + have`. The
scale exceeds any plausible ingredient count, so `have` can never outrank a
lower `missing`, and results need one sort key instead of two scripts.

**Cache invalidation is handled by the key, not by signals.** The cache key
contains a hash of the pantry's ingredient ids, so changing the pantry
changes the key and a stale entry becomes unreachable rather than wrong.
Nothing has to notice the write. A useful consequence: removing an
ingredient and adding it back reuses the earlier entry, because the pantry
is genuinely in the same state.

Quantities are excluded from that hash — coverage is presence-based, so
`2 onions` to `3 onions` cannot change a result and should not cost a miss.

**Elasticsearch is selected when reachable, SQL is the fallback.** The
comparison command establishes they agree, which is what makes automatic
fallback a latency change rather than a correctness one. The UI shows which
backend answered and whether the response was cached, so both are
observable rather than asserted.

**Coverage counters are denormalised onto `Recipe`.** They sit in the
ranking query, and counting across 2.09M rows per request would be the
whole latency budget. They go stale if the vocabulary changes — acceptable,
because that already requires a reimport and they are recomputed then.

**Moods map to corpus tags, not to a model.** 23 named tag sets, queried
through a GIN index. Tags within a mood are OR, moods in one request are
AND. Deterministic, testable, changeable in one file.

Two tag classes were deliberately avoided: taxonomy headers like
`preparation` (230,546 recipes) and `course` (218,148) sit on ~95% of the
corpus, so filtering on them is a no-op that looks like a filter; and
near-universal values like `easy` (54% of the corpus) would swamp any mood
containing them.

**The search store carries a request sequence counter.** Dragging the
threshold slider fires several requests, and whichever the server finishes
last would otherwise win — which is not necessarily the one matching the
current filters. Filter changes are debounced to reduce how many requests
are sent; the counter discards the ones that still overlap. Either alone
leaves a gap.

**A saved-recipe flag is deliberately absent from search results.** The
recommendation payload is cached on a key accounting for the pantry and
query but not per-user state, so `/recipes/saved/ids/` returns a bare id
list the client merges instead. One small uncached call is cheaper than
making the expensive cached one user-specific.

**nginx serves static files and proxies the rest to gunicorn.** Serving
assets through an application server wastes a worker slot per request.

**TLS settings are environment-gated.** `SECURE_SSL_REDIRECT`, secure
cookies and HSTS default to on but can be switched off, because prod
settings over plain HTTP redirect every request to a scheme nothing is
listening on. HSTS in particular is tied to the same switch: sending it
from a localhost instance pins the browser to HTTPS for `localhost` for a
year and breaks every other local project on the machine.

---

## Known limitations

**Coverage is presence-based, not quantity-based.** The system knows you
have flour, not whether you have two cups. Comparing `2 cups flour` to
`500 g flour` needs per-ingredient density data no public recipe dataset
ships. Units are normalised within a dimension (g↔kg, tsp↔cup); mass and
volume are never interconverted. Extension path: a density column on
`Ingredient`.

**13% of ingredient strings do not resolve.** They show as unknown and
count as missing. Conservative on purpose.

**Irregular plurals.** `_singular()` handles `-s`, `-ies`, `-oes` and some
`-es` cases, so `leaf`/`leaves` never meet. Worth ~0.1%, and the fix is an
irregular-plural map that grows forever.

**Ambiguous generics.** `oil`, `cheese` and `nuts` name categories. Generic
ingredients exist, but a pantry with olive oil does not satisfy a recipe
asking for oil. That needs a parent/child relationship on `Ingredient`.

**Documented ambiguity calls.** `coriander` → leaves. `red pepper` → bell
pepper, since `red pepper flakes` has its own entry. `tomato sauce` →
canned tomato, not ketchup. All chosen for American usage, matching the
corpus, and all one line to change.

**Recipe titles are reconstructed.** The corpus stripped apostrophes before
storing, so `Ree Ree's Chicken` arrives as `ree ree s chicken`.
Reattaching the apostrophe is a guess — right often enough here to be worth
making, wrong for any recipe legitimately containing a standalone "s".

**Migrations run on container start.** Convenient for one instance, wrong
for several — two containers booting together would both attempt it. In a
real deployment this belongs in a release step.

**Login throttling is a global anon rate**, not a scoped throttle on the
login view. 30/min is generous for password guessing; tightening it needs
per-view configuration.

**Not deployed, deliberately.** No free tier fits the stack: the
Elasticsearch container alone is configured with a 512MB JVM heap, which
equals Render's entire free-tier memory budget, and Railway and Fly no
longer offer usable free tiers. Running locally is also better for a
walkthrough — full corpus, 30ms searches, no cold starts. The SQL fallback
means a deployment without Elasticsearch would still work, at 170ms.

---

## Stack

- **Backend** — Django 5, DRF, service-layer architecture, split settings
- **Data** — PostgreSQL 16, Elasticsearch 8.13, Redis 7
- **Serving** — gunicorn behind nginx, all in Docker Compose
- **Frontend** — React 19, TypeScript, Vite, Zustand, Tailwind 4

```
backend/
├── config/          settings (base/dev/prod), root urls
├── core/            base models, pagination, typed exceptions, seed_demo
├── users/           custom user model, JWT auth
├── ingredients/     vocabulary, units, matcher, corpus mining
├── pantry/          pantry items and audit log
├── recipes/         corpus, ES mapping, import, recipe book
├── recommendations/ coverage ranking, moods, caching
├── nginx/           reverse proxy config
├── data/            seed vocabulary (raw corpus gitignored)
└── tests/           120 tests

frontend/src/
├── api/             axios client with JWT refresh, per-domain modules
├── store/           zustand: auth, pantry, search
├── pages/           auth, pantry, audit log, search, recipe detail, book
├── components/      layout shell and shared UI primitives
└── utils/
```

---

## Running it

### Everything in containers

```bash
cd backend
cp .env.example .env          # fill in the values
docker compose up -d --build
```

Starts Postgres, Redis, Elasticsearch, Django under gunicorn, and nginx.
The app container waits for Postgres, migrates, loads the ingredient
vocabulary, and collects static files before serving.

**http://localhost:8080**

nginx returns 502 for the ~15 seconds the app spends migrating on boot.
Wait for `docker compose ps` to show `web` as healthy.

`docker compose down` preserves the named volumes. `down -v` wipes them and
means reimporting the corpus.

### Development

Dependencies in containers, app and frontend on the host:

```bash
cd backend
docker compose up -d db redis elasticsearch
source venv/bin/activate
python manage.py runserver
```

```bash
cd frontend
npm install
npm run dev
```

Vite proxies `/api` to port 8000.

### Recipe corpus

Needs `RAW_recipes.csv` from the
[Food.com Kaggle dataset](https://www.kaggle.com/datasets/shuyangli94/food-com-recipes-and-user-interactions)
at `backend/data/raw/`. The directory is mounted read-only into the
container rather than baked into the image.

```bash
python manage.py import_recipes      # ~108s
python manage.py index_recipes       # ~9s
```

The app works without the corpus — search just returns nothing.

### Demo account

```bash
python manage.py seed_demo --reset
```

Creates a user with an 18-item pantry written the way a person types, so
the matcher is visibly doing work rather than assumed to. One entry is
deliberately unresolvable. Prints credentials and a suggested walkthrough.

### Tests and measurement

```bash
pytest                               # 120 tests
python manage.py mine_vocabulary     # matcher coverage against the corpus
python manage.py compare_search      # SQL vs Elasticsearch
```

---

## API

### Auth
| Method | Path |
|---|---|
| POST | `/api/v1/auth/register/` |
| POST | `/api/v1/auth/login/` |
| POST | `/api/v1/auth/token/refresh/` |
| GET | `/api/v1/auth/profile/` |

Passwords are checked against Django's configured validators. Anonymous
requests are throttled. Refresh tokens rotate and old ones are blacklisted.

### Pantry
| Method | Path | Purpose |
|---|---|---|
| GET/POST | `/api/v1/pantry/` | List or add items |
| PATCH/DELETE | `/api/v1/pantry/{id}/` | Update or remove |
| GET | `/api/v1/pantry/logs/` | Audit trail |
| GET | `/api/v1/pantry/expiring/?days=7` | Approaching expiry |

### Search
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/recommendations/` | Ranked recipes |
| GET | `/api/v1/recommendations/moods/` | Mood catalogue (public) |
| GET | `/api/v1/recommendations/recipes/{id}/` | Detail with have/missing state |

Search parameters:

| Param | Default | Meaning |
|---|---|---|
| `max_missing` | 0 | Ingredients you will buy |
| `min_required` | 3 | Ignore trivially small recipes |
| `max_minutes` | — | Cook time ceiling |
| `mood` | — | Comma-separated mood keys, AND-ed |
| `order` | best | `best`, `quickest`, `simplest` |
| `limit`, `offset` | 20, 0 | Pagination |
| `backend` | auto | `sql` or `es`, for benchmarking |

### Recipe book
| Method | Path | Purpose |
|---|---|---|
| GET/POST | `/api/v1/recipes/saved/` | List or save |
| PATCH/DELETE | `/api/v1/recipes/saved/{recipe_id}/` | Notes, or remove |
| GET | `/api/v1/recipes/saved/ids/` | Bare id list for marking results |

All list endpoints are paginated. Errors share one shape:

```json
{"error": {"message": "...", "code": "...", "status_code": 400, "fields": {}}}
```

---

## Licence

MIT.