# MDR Reuse

Reuse labour documentation (WHO Labour Care Guide) in a Facility-Based Maternal
Death Review (Form 4), with provenance: nothing re-keyed, nothing claimed that
was not recorded.

Agent handoff: [`AGENTS.md`](AGENTS.md). Design: [`docs/design.md`](docs/design.md).
To-do: [`TODO.md`](TODO.md).
Dependencies: [`docs/dependencies.md`](docs/dependencies.md). Evidence map:
[`docs/evidence-map.md`](docs/evidence-map.md). UI principles:
[`docs/ui.md`](docs/ui.md). LCG storage model:
[`docs/lcg-storage.md`](docs/lcg-storage.md). Generated overlap inventory:
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

The guide itself is registered: **7 sections, 34 variables**, in printed order, with
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

**Value rules are enforced in Postgres.** A trigger rejects an observation whose
enum value is not on the printed chart, whose number falls outside the row's
range, whose unit does not match, or whose stage is not first/second.
`Observation.clean()` mirrors it for friendly form errors. Clinical thresholds
(what counts as an alert) stay in application code, because they change with the
guideline; what the form permits does not.

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

## Current state

Read [`AGENTS.md`](AGENTS.md) for the full agent handoff, current behavior and
remaining work. Read [`TODO.md`](TODO.md) for the authoritative task list.

- Form 4: 14 sections, **99 fields**, three block schemas.
- LCG: 7 sections, 34 variables, Postgres-validated observations.
- Cases 0 and A seeded; review creation works with or without a labour record.
- Proposals, provenance drawer, derived calculations, accept/reject/correct.
- Conditional Form 4 (`c2`), corrections with supersession and history.
- Pre-submission checks (`k3`), including Not known and N/A distinctions.
- Submit → return with per-field comments → resubmit → approve; frozen versions.
- HTML/JSON output from a version.

Not yet complete: amendments, output provenance appendix, missing-observation
marker, security hardening/scoping, overlap write-up and demo script. See
`TODO.md` and `AGENTS.md`; do not treat the limitations as solved.
