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
docker compose exec web python manage.py seed_case_0   # complete normal labour
docker compose exec web python manage.py seed_case_a   # death review
```

Open http://127.0.0.1:8000

| User | Password | Role |
|---|---|---|
| `resident` | `resident123` | author |
| `fno` | `fno123` | approver |

Reset the demo (TRUNCATE bypasses the append-only row triggers):

```sh
docker compose exec web python manage.py flush --no-input
docker compose exec web python manage.py seed_case_0
docker compose exec web python manage.py seed_case_a
```

## Tests

```sh
uv run pytest
```

(or `docker compose exec web python -m pytest` once dev dependencies are in the
image; the compose image is built without them).

## The LCG as data

The guide itself is registered: **7 sections, 33 variables**, in printed order, with
type, unit and the ALERT rule for each (`review/registry_lcg.py`). Observations
reference a variable — never a free-text kind — so a typo fails at insert time.

Read a chart like the paper form:

```sh
docker compose exec db psql -U mdr -d mdr \
  -c "select section, variable, cells from lcg_chart where patient = 'Meena Kulkarni' order by section_ord, row_ord;"
```

Three views render the chart:

- `lcg_chart` — one row per variable, cells across time in IST.
- `lcg_cells` — one row per cell with a computed column number and stage.
- `lcg_header` — Section 1 expanded from `SourceDocument.header_json`.

Every observation carries `stage` (`first` / `second`) on the row itself, alongside
`variable`, `observed_at`, `author` and the three timestamps. Case 0 has 54
second-stage cells (23:00 and 23:15); case A is entirely first stage.

```sh
docker compose exec db psql -U mdr -d mdr \
  -c "select col, chart_time, stage, count(*) from lcg_cells where patient='Meena Kulkarni' group by 1,2,3 order by 1;"
```

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
- LCG registry: 7 sections, 34 variables, ordered and typed; observations FK to a
  variable and carry `stage` on the row. `lcg_chart` and `lcg_cells` views render
  the grid.
- Case 0: a complete, normal labour — every grid variable across ten first-stage
  columns and two second-stage columns, 322 observations, no death.
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
