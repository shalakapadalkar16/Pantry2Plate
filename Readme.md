# Engineering Log — Append: Packaging and Hardening

Paste after section 17, then replace sections 9 and 10 with the versions at
the bottom.

---

## 18. Containerizing the application

Before this, `docker compose up` started Postgres, Redis and Elasticsearch.
Django ran on the host under `runserver`. So "containerized deployment"
described the dependencies, not the application — the exact kind of claim
that reads fine in a README and falls apart when someone clones the repo.

Now: `Dockerfile`, an entrypoint, and `web` plus `nginx` services. One
command brings up the whole stack.

### Decisions worth explaining

**Single stage, not multi-stage.** The usual argument for multi-stage is
keeping compilers out of the final image, but `psycopg2-binary` ships wheels
and nothing else here needs a build toolchain. A second stage would add
complexity for no size saving. Multi-stage is a good default, not a rule.

**Requirements copied and installed before the source.** Docker invalidates
every layer after a changed one, so copying code first means a one-line edit
reinstalls all dependencies. Splitting them means the pip layer is cached
until `requirements.txt` actually changes.

**`PYTHONUNBUFFERED=1`.** Without it Python buffers stdout and
`docker compose logs` shows nothing until the buffer flushes, so a crash
looks like a hang. Small setting, disproportionate debugging cost.

**Non-root user.** A process that does not need to write to the image should
not be able to.

**nginx serves static, proxies the rest.** gunicorn is an application
server; serving assets through it consumes a worker slot per request for
work nginx does better. `collectstatic` writes into a named volume that
nginx mounts read-only.

**The 280MB corpus is bind-mounted, not copied.** Two management commands
read it. Baking it in would slow every image build for a file the running
app never touches.

**`depends_on: condition: service_healthy`.** Replaces the manual "wait 25
seconds for Elasticsearch" the README previously had to document. The
healthchecks already existed; nothing was waiting on them.

### The settings bug this exposed

`prod.py` had `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE` and
`CSRF_COOKIE_SECURE` unconditionally `True`, plus a year of HSTS.

That is correct for a public HTTPS deployment and wrong everywhere else.
Over plain HTTP, Django redirects every request to `https://` where nothing
is listening, so the browser loops. Secure cookies are never sent, so login
fails with no error. All three are now environment-gated.

**HSTS is the one that matters most.** It is tied to the same switch,
because a localhost instance sending HSTS pins the browser to HTTPS for
`localhost` for a year — which then breaks every other local project on the
machine, with a cause nobody would guess from the symptom.

### One limitation to state honestly

The entrypoint runs `migrate` on start. Fine for one container, wrong for
several — two booting together would both attempt it. Django wraps
migrations in a transaction so the loser fails rather than corrupting
anything, but in a real deployment this belongs in a release step.

---

## 19. Auth hardening

Four gaps, and the pattern connecting them is worth naming: **every one was
something configured and then never connected.** Configuration that looks
right and does nothing is harder to spot than configuration that is absent.

**Password validators.** `AUTH_PASSWORD_VALIDATORS` was set in `base.py` in
the first sprint. `ModelSerializer` never calls it. The only rule in force
was `min_length=8`, so `12345678` and `password` both registered
successfully. Verified before and after: 400, 400, 201.

**No throttling.** Login and register were unlimited. `AnonRateThrottle` at
30/min now applies globally, which is the one-line version — a scoped
throttle on the login view would be tighter and needs per-view
configuration.

**Refresh rotation without a blacklist.** `ROTATE_REFRESH_TOKENS` was
`True`, `BLACKLIST_AFTER_ROTATION` was `False`, and the `token_blacklist`
app was not installed. So rotation issued a new refresh token and left the
old one valid until natural expiry. Rotation exists to invalidate the
previous token; without the blacklist it buys close to nothing while looking
like it does.

**No LOGGING config.** Console handler only, deliberately. In a container
stdout *is* the log — Docker, Compose and every orchestrator collect it.
Writing to a file inside a container puts logs where nobody looks and
nothing rotates. `django.db.backends` is wired up at WARNING so query
logging can be switched on by env var when hunting N+1s.

**Say this in an interview:** the useful lesson is not "remember to add
throttling." It is that four separate settings looked correct in review and
had no effect at runtime, and none of them were caught by tests, because a
test asserting "weak password is rejected" did not exist. Configuration is
not behaviour until something exercises it.

---

## Replacement for section 9 — Current state

**Working end to end:** auth with real password validation, throttling and
token blacklisting · pantry CRUD with audit log and expiry ·
294-ingredient vocabulary at 87% corpus coverage · 231,637 recipes and
2.09M ingredient rows · coverage ranking · 23 moods · Elasticsearch
retrieval at 5x SQL, verified equivalent · Redis caching at 1.5ms warm ·
saved recipe book · fully containerized stack · 120 tests

**Not built:** frontend for recipe search (pantry and auth UI exist) ·
public deployment

**Honest read:** the backend is finished. `docker compose up --build`
produces a running application at localhost:8080, and every performance
claim in the README is reproducible with a management command. Nothing in
the repo now describes something that does not exist.

Deployment was evaluated and skipped deliberately, not deferred: no free
tier fits the stack — the Elasticsearch container alone is configured with a
512MB JVM heap, which equals Render's entire free-tier memory budget, and
Railway and Fly no longer offer usable free tiers. For a demo recording,
running locally is also strictly better: full corpus, 30ms searches, no
cold starts.

---

## Replacement for section 10 — Next steps

Backend is complete. What remains is presentation.

1. **Frontend for search** — result list, missing-count threshold control,
   mood filters, recipe detail, recipe book. Auth and pantry screens exist,
   so this is four new screens in an existing app, roughly 9 hours.
2. **Demo recording** — a `seed_demo` command creating a user with a
   realistic 15-item pantry, so the video does not open with typing
   ingredients into a form. Worth also showing `compare_search` in a
   terminal; the SQL-versus-Elasticsearch table is more convincing than any
   UI screen and takes ten seconds.

Smaller items, none of which change what the project can claim:

- Scoped login throttle rather than a global anon rate
- Migrations moved out of the container entrypoint into a release step
- Irregular-plural handling in the normalizer (`leaf`/`leaves`)
- Parent/child ingredients so olive oil satisfies a recipe asking for oil

---

## Appendix additions — interview answers

**"Tell me about a class of bug you have learned to look for."**
Configuration that looks correct and does nothing. On this project four
separate settings fell into that category: password validators set but never
called by the serializer, a pagination class configured but ignored because
`APIView` does not use it, refresh-token rotation enabled without the
blacklist app that makes it meaningful, and a mood filter clause that had
never once executed and turned out to contain a Postgres type error. None
were caught by review or by tests, because no test asserted the behaviour —
only the setting existed. Now I test the behaviour, not the config.

**"How do you decide when a default is wrong?"**
The Dockerfile is single-stage, which goes against the usual advice. The
reason multi-stage exists is to keep build toolchains out of the final
image, and this project has no build toolchain — `psycopg2-binary` ships
wheels. Following the pattern would have added a stage and saved nothing. I
try to know what a convention is protecting against before applying it.

**"A bug whose symptom would not have led you to the cause."**
`prod.py` enabled HSTS unconditionally. Running that locally would have
pinned my browser to HTTPS for `localhost` for a year, breaking every other
local project on the machine — and the symptom would have appeared weeks
later in an unrelated repo. I caught it while gating `SECURE_SSL_REDIRECT`
for the container and realised HSTS belonged behind the same switch.