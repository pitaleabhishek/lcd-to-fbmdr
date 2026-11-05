# MDR Reuse

Reuse labour documentation (WHO Labour Care Guide) in a Facility-Based Maternal
Death Review (Form 4), with provenance: nothing re-keyed, nothing claimed that
was not recorded.

Design: [`docs/design.md`](docs/design.md). Generated overlap inventory:
[`docs/inventory.md`](docs/inventory.md). Form 4 source text used for
reconciliation: [`docs/form4-source.txt`](docs/form4-source.txt).

## Run

Everything runs in Docker. Memory is capped at 160 MB for Postgres and 224 MB
for the app; measured idle footprint is ~140 MB total.

```sh
docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py seed_case_a
```

Open http://127.0.0.1:8000

| User | Password | Role |
|---|---|---|
| `resident` | `resident123` | author |
| `fno` | `fno123` | approver |

Reset the demo (TRUNCATE bypasses the append-only row triggers):

```sh
docker compose exec web python manage.py flush --no-input
docker compose exec web python manage.py seed_case_a
```

## Tests

```sh
uv run pytest
```

(or `docker compose exec web python -m pytest` once dev dependencies are in the
image; the compose image is built without them).

## Regenerate the inventory

```sh
docker compose exec web python manage.py build_inventory
```

Writes `docs/inventory.csv` and `docs/inventory.md`. The inventory is an output
of the registry, never hand-maintained.

## What exists (day 1)

- All domain models, migrations, and Postgres triggers that make recorded facts
  append-only (`Observation`, `SourceDocument`, `Delivery`, `Death`, `CareContact`).
- Registry with full-word section keys and `f4.<section>.<label>` grammar
  (53 fields in the first slice).
- 18 rules producing proposals with frozen inputs; `NotComputable` keeps
  missing / unknown / not-applicable apart.
- Case A seeded: charted labour, an alert crossing, one missed observation, a
  late entry (documented after death), a PPH death.
- Accept / reject / correct, submit, approve, reproducible output from a version,
  and a JSON payload that includes gaps rather than omitting them.
- Inventory reconciled against the extracted Form 4 text: 53 of 53 labels found;
  2 fields (3.8%) sourced from the LCG.

Not built yet: blocks (referral, neonatal, transfusion, interventions matrix),
the amendment workspace, HTMX partials, and the remaining ~100 fields.
