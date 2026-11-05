# Dependency register

Every component that ships with the prototype, why it is there, and how it is
maintained. Versions are pinned in `pyproject.toml` and `uv.lock`; the Docker image
installs from the lock.

## Runtime

| Component | Version | Licence | Why this | Maintenance |
|---|---|---|---|---|
| Python | 3.12 (image) / 3.13 (host venv) | PSF-2.0 | Baseline for the stack; 3.12 is the image tag | Security fixes until Oct 2028 (3.12) |
| Django | 5.2.19 | BSD-3-Clause | The assignment is a forms-and-workflow app: ORM, migrations, auth, templates, CSRF, transactions. A framework that already has these is less code than assembling them | Active LTS; supported until April 2028 |
| psycopg | 3.3.8 (`psycopg[binary]`) | LGPL-3.0-only | PostgreSQL driver; first-class `jsonb` support for block answers and frozen inputs | Active; used by Django's own PG backend |
| PostgreSQL | 17 (alpine image) | PostgreSQL License | `jsonb` for `value_json`/`payload_json`, and row triggers for append-only facts and value validation. Both are load-bearing in the design, not conveniences | Supported until 2029 |

## Development and test

| Component | Version | Licence | Why this | Maintenance |
|---|---|---|---|---|
| uv | 0.10.0 | Apache-2.0 OR MIT | Reproducible installs from a lockfile; one tool for venv and add/remove | Active (Astral) |
| pytest | 9.2.0 | MIT | Test ergonomics: plain asserts, fixtures, parametrisation | Active |
| pytest-django | 4.14.0 | BSD-3-Clause | Database setup/teardown and `client`/`django_user_model` fixtures without boilerplate | Active |

## Transitive only

`asgiref` (BSD-3), `sqlparse` (BSD-3), `tzdata` (Apache-2.0), `packaging` (Apache-2.0
or BSD-2), `pluggy` (MIT), `iniconfig` (MIT), `Pygments` (BSD-2), `colorama` (BSD-3).
None is used directly.

## Deliberately not included

| Thing | Why not |
|---|---|
| A JavaScript framework (React/Vue) | The product is forms; server-rendered HTML plus ~200 lines of JS is less to maintain and keeps the source of truth on the server |
| A component library / Tailwind build | One hand-written stylesheet is enough for the screens; a build step buys nothing here |
| HTMX | Planned for partial updates; not needed yet because autosave is a small fetch and everything else is POST/redirect. Adding it later is a script tag, not a dependency decision |
| A charting library | The LCG chart is deliberately not rendered (assignment defers it) |
| Celery / Redis | `reevaluate(pregnancy)` is synchronous by design at this scale |
| FHIR libraries | Decided against: see `docs/design.md` §14 |
| Docker Compose | Development runtime, not shipped to users |

## Pinning policy

- `pyproject.toml` holds the major pin (`django>=5.2,<6.0`); `uv.lock` holds exact
  versions and hashes.
- The Docker image runs `uv sync --frozen --no-dev`, so it installs exactly the lock.
- No dependency is added without a line in this register.
