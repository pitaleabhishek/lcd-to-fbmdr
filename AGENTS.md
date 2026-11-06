# Agent handoff — MDR Reuse

Read this first. It describes the current repository state, not the original
seven-day plan. `TODO.md` is the living task list; `docs/design.md` is the
architectural reference.

## What this is

A Django prototype for reusing a WHO Labour Care Guide (LCG) labour record in a
Facility-Based Maternal Death Review (Form 4), with provenance:

- source facts are append-only and corrected by a new row with `supersedes`;
- a review proposes values from the source, and the clinician accepts, rejects
  or corrects each one;
- Form 4 is conditional, checks its answers before submission, and freezes the
  submitted payload;
- nothing is invented: missing, unknown, N/A and unsupported conclusions stay
  distinct.

## Current state

- Commit at handoff: see `git log -1` (working tree should be clean).
- Tests: **170 passing**.
- Active registry: **14 sections, 99 Form 4 fields**, three block schemas,
  **34 LCG variables**.
- Conditions: `c2` — 2 section gates, 33 field rules.
- Checks: `k3` — 14 check groups, run on Submit.
- Rules: 17 proposal rules.
- Demo data: Case 0 (complete labour) and Case A (death after charted labour)
  are seeded in the development database. Do not reset demo data unless asked.
- Dev DB may contain one retained legacy `Form4Field` row for a retired field;
  the active registry is still 99. Fresh test databases show 99.

## Run

Docker is the documented path:

```sh
docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py seed_case_0
docker compose exec web python manage.py seed_case_a
```

Open http://127.0.0.1:8000

| User | Password | Role |
|---|---|---|
| `resident` | `resident123` | author |
| `fno` | `fno123` | FNO / approver |

Tests in this workspace:

```sh
.venv/bin/pytest -q
```

Management commands can also be run locally:

```sh
.venv/bin/python manage.py check
.venv/bin/python manage.py migrate
.venv/bin/python manage.py build_inventory
```

Database shell:

```sh
docker compose exec db psql -U mdr -d mdr
```

Reset demo data only when explicitly requested:

```sh
docker compose exec web python manage.py flush --no-input
docker compose exec web python manage.py seed_case_0
docker compose exec web python manage.py seed_case_a
```

## URLs

- `/` — review index, source link, new review
- `/review/new/` — start a review with or without a labour record
- `/review/<pk>/` — review workspace
- `/review/<pk>/output/` — printed Form 4 from a frozen version; `?format=json`
- `/review/<pk>/history/` — versions, returns, activity
- `/labour/<pk>/` — labour chart, add observation, correct value
- `/labour/<pk>/history/` — labour record history
- `/labour/<pk>/review/` — one-click start from a labour record

## Architecture map

- `review/models.py` — domain models, append-only triggers, `ReviewItem` states.
- `review/registry.py` — Form 4 sections/fields/blocks, `LEGACY_FIELDS`.
- `review/registry_lcg.py` — LCG sections/variables.
- `review/conditions.py` — conditional visibility (`c2`), three-valued logic.
- `review/checks.py` — pre-submission checks (`k3`).
- `review/source_time.py` — current source heads and precision-aware comparisons.
- `review/rules.py` — proposals and derived values.
- `review/thresholds.py` — LCG alert crossings (`lcg_2021@1`).
- `review/evidence.py` — LCG→Form 4 evidence edges.
- `review/services.py` — answers, proposals, submit/return/approve, payloads.
- `review/views.py` — pages, workspace, output, source drawer, actions.
- `review/templates/review/` — UI.
- `tests/` — pytest suite.

## Important design invariants

- **Recorded source facts are never edited.** Corrections create a new row with
  `supersedes`; readers use the current head.
- **Alerts are code, not data.** Thresholds live in `thresholds.py` and are
  versioned/cited. What the form permits is enforced by Postgres triggers.
- **Conditions hide, they do not answer.** Hidden is not N/A. Hidden answers are
  retained and shown in the “not shown” tray; they never print.
- **Frozen versions win.** Submitted/approved output comes from the version
  payload. Do not recalculate an old output from current data or silently relink
  a frozen review.
- **Not known ≠ N/A.** Not known means the question applies but the answer is
  unavailable; it requires a reason and is attributed. N/A means the question
  does not apply.
- **No unsupported clinical arithmetic.** No parity/living-children rules, no
  diagnosis-versus-observation inference, no suggested causes.
- **Finish small.** Use focused commits; this project has a large test suite and
  broad behavior changes are easy to break.

## Conditional form

`conditions.py` owns visibility. Unanswered controllers fail open (show the
question); a definite excluded answer hides it. Unknown ANC answers use a
targeted `WhenYes` that treats `unknown` as uncertainty, not a definite no.
Specification fields are required when their option is selected even if an
upstream answer is unknown.

Do not reintroduce the retired `f4.delivery.neonatal_death_time`. It was a
misread of the maternal post-birth bands. The active field is
`f4.delivery.post_birth_complication_time`, gated on
`f4.delivery.phase = post_birth`. Old answers remain in `LEGACY_FIELDS` and are
never mapped onto the new field.

## Checks

Checks run only when Submit is pressed. Errors block; warnings require one
“Submit anyway” confirmation. The panel shows after Submit and the resident note
survives a blocked attempt. `CHECK_VERSION = "k3"` is in the frozen payload and
the submission audit event.

Current check groups include:

- required fields; N/A on a required question is an error;
- conditional missing follow-ups, preserving the documented warning/error policy;
- reconsideration after changed evidence;
- current source records, source corrections, multiple current records;
- precision-aware impossible dates/late entries;
- review-value validation (age, counts, durations, ICU);
- interval/transfusion/neonatal consistency warnings;
- retained answers, late entries, missing summary, no labour record.

See `docs/checks.md`. Do not turn every optional field into a blocker.

## What is done from the brief

- Labour records, add/view, corrections, history.
- Review linked to source with or without a labour record.
- Proposed reuse with provenance and derived calculations.
- Clinician accept/reject/correct; source remains immutable.
- Conditional Form 4, resumable, all 99 fields.
- No unsupported conclusions.
- Late entries visible; missing observations only partly addressed.
- Checks before submission.
- Roles, return-with-comments, approval, frozen versions.
- Structured output from versions.

## What remains

See `TODO.md` for the authoritative list.

1. **Amendments** — approved reviews are frozen; the `Amendment` model exists but
   no workflow/UI/output. This is the largest explicit brief gap.
2. **Output provenance appendix** — origin chips exist, but no per-value “from
   where” appendix in the printed output.
3. **Missing-observation marker** — late entries are visible; a gap between
   chart columns (e.g. Case A 20:30→22:30) is still implicit.
4. **Security note and gaps** — app connects as table owner; no per-user/facility
   object scoping; no login throttling. Do not claim these are solved.
5. **Overlap analysis write-up** — `docs/inventory.md` is generated; the
   narrative per Dr Atter’s four categories is not written.
6. **Demo script** and final limitations note.

Cases B/C/D are fixture work, not required. The no-labour-record path and
referral-after-delivery behavior exist; add cases only if a demo needs them.

## Known uncertainties / do not overclaim

- `discharged_at` is treated as administrative closure. If it is after death,
  `timing.c` uses death as the clinical exit. This is an implementation
  interpretation, not a verified government rule.
- Estimated timestamps cannot establish ordering; date-only same-day is
  uncertain. Future date-only dates are caught; estimated future dates are not.
- Interval consistency uses a one-minute tolerance.
- Multiple current death/delivery records produce warnings; checks use the latest
  clinical time as a deterministic fallback.
- The PDF does not explicitly settle stillbirth cause capture, referral-table
  availability or abortion anaesthesia; see `docs/conditions.md` for the
  implementation interpretations.

## Reference documents

- `docs/design.md`
- `docs/conditions.md`
- `docs/checks.md`
- `docs/lcg-storage.md`
- `docs/evidence-map.md`
- `docs/dependencies.md`
- `docs/inventory.md`
- `docs/form4-source.txt`
- `TODO.md`
