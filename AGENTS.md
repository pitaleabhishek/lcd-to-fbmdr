# Agent handoff — LCG to FBMDR

Read this file first. It describes the current repository. It is not the original
seven-day plan. `TODO.md` is the task list. `docs/design.md` is the architecture
reference.

## What this is

This is a Django prototype. It reuses a WHO Labour Care Guide (LCG) labour record
in a Facility-Based Maternal Death Review (Form 4). Each value keeps its source.

- Source facts are append-only. A correction is a new row with `supersedes`.
- A review proposes values from the source. The clinician accepts, rejects or
  corrects each value.
- Form 4 is conditional. The app checks answers before submission. It freezes the
  submitted payload.
- The app does not invent data. Missing, unknown, N/A and unsupported conclusions
  stay separate.

## Current state

- Commit at handoff: see `git log -1`. Commit the amendment work before handoff.
- Tests: **280 passing**.
- Active registry: 14 sections, 99 Form 4 fields, three block schemas and 34 LCG
  variables.
- Conditions: version 2. It has 2 section gates and 33 field rules.
- Checks: version 3. It has 14 check groups. Only a required clinical judgement
  blocks submit; every other finding is frozen and shown to the FNO.
- Rules: 44 proposal rules.
- Documents: eight record sources. 76 fields are document-sourced, 44 are wired
  to a rule, 23 are clinical judgement. See `docs/quick-sources.md`.
- Provenance: version 1. The app freezes a snapshot for each value at submit and
  amendment submit. It checks the snapshot at approval.
- Demo data: Cases A, B, C, D and the Happy case are seeded. Cases B and C are
  blank drafts with proposals. Case D is a complete draft. `seed_case_0` remains
  an optional LCG chart fixture. Do not reset demo data unless asked.
- The dev DB may have one retained legacy `Form4Field` row. The active registry
  still has 99 fields. Fresh test databases show 99.

## Run

Use Docker:

```sh
docker compose up -d --build
docker compose exec web python manage.py demo_setup
```

Open http://127.0.0.1:8000.

Optional TLS profile with Caddy and an internal CA on port 9443:

```sh
SECURE=1 TRUST_PROXY=1 ALLOWED_HOSTS=localhost,127.0.0.1 \
CSRF_TRUSTED_ORIGINS=https://localhost:9443 \
SECRET_KEY='<long random>' \
docker compose --profile tls up -d --build
```

Postgres TLS is on by default. The app connects with `DB_SSLMODE=require`.

Make an encrypted backup:

```sh
BACKUP_PASSPHRASE=... ./scripts/backup-db.sh
```

### Deploy workflow

Change the hosted demo first, check it there, then merge the code. The deploy
target is `nirovia-api1:/home/nirovia/lcgtomsrd`; the web container binds
`./review` and runs gunicorn on `127.0.0.1:8800`.

```sh
rsync -av --delete --exclude '__pycache__' --exclude '*.pyc' \
  review/ nirovia-api1:/home/nirovia/lcgtomsrd/review/
rsync -av docs/ nirovia-api1:/home/nirovia/lcgtomsrd/docs/
ssh nirovia-api1 'cd /home/nirovia/lcgtomsrd && \
  docker compose -f docker-compose.yml -f docker-compose.deploy.yml restart web'
```

Templates and docs are live through the bind mount; Python changes need the
restart. Do not sync `.env`. No migrations are needed unless a model changed.

| User | Password | Role |
|---|---|---|
| `resident` | `resident123` | author |
| `fno` | `fno123` | FNO / approver |

Run tests in this workspace:

```sh
.venv/bin/pytest -q          # 8 xdist workers, about 20 seconds
.venv/bin/pytest -q -n 0     # one process for debugging
```

Run management commands locally:

```sh
.venv/bin/python manage.py check
.venv/bin/python manage.py migrate
.venv/bin/python manage.py build_inventory
```

Open the database shell:

```sh
docker compose exec db psql -U mdr -d mdr
```

Reset demo data only when asked:

```sh
docker compose exec web python manage.py flush --no-input
docker compose exec web python manage.py demo_setup
```

## URLs

- `/`: review index, source link and new review.
- `/review/new/`: start a review with or without a labour record.
- `/review/<pk>/`: review workspace.
- `/review/<pk>/output/`: Form 4 from a frozen version. Add `?format=json` for
  JSON. The current approved version has a clean print copy.
- `/review/<pk>/form1/`: Form 1 for the same review.
- `/review/<pk>/form1/save/`: POST Form 1 details.
- `/review/<pk>/provenance/<field>/`: per-field provenance. Add `?version=N` for
  an old version.
- `/review/<pk>/amend/<amendment>/`: amendment workspace.
- `/review/<pk>/amend/<amendment>/quick/`: clinical amendment page for the author.
- `/review/<pk>/amend/<amendment>/output/`: pending amendment output. It has a
  DRAFT stamp.
- `/review/<pk>/history/`: versions, amendments, returns and activity.
- `/labour/<pk>/`: labour chart, add observation and correct value.
- `/labour/<pk>/history/`: labour record history.
- `/labour/<pk>/review/`: start a review from a labour record.

## Architecture map

- `review/models.py`: domain models, append-only triggers and `ReviewItem` states.
- `review/scope.py`: live answers and staged amendment answers. Always use it.
- `review/provenance.py`: per-value snapshot (version 1), hashing and old-version
  fallback.
- `review/form1.py`: Form 1 mapping, Form 1 fields and occurrence flags.
- `review/registry.py`: Form 4 sections, fields, blocks, `LEGACY_FIELDS` and the
  eight-document source map (`DOCUMENTS`, `FIELD_DOCUMENT`, `CLINICIAN_KEYS`).
- `review/registry_lcg.py`: LCG sections and variables.
- `review/conditions.py`: conditional visibility (version 2) with three-valued logic.
- `review/checks.py`: pre-submission checks (version 3).
- `review/source_time.py`: current source heads and precision-aware comparisons.
- `review/rules.py`: proposals and derived values.
- `review/thresholds.py`: LCG alert crossings (`lcg_2021@1`).
- `review/evidence.py`: LCG to Form 4 evidence links.
- `review/services.py`: answers, proposals, submit, return, approve and payloads.
- `review/views.py`: pages, workspace, output, source drawer and actions.
- `review/templates/review/`: UI.
- `tests/`: pytest suite.

## Design rules

- **Do not edit recorded source facts.** A correction is a new row with
  `supersedes`. Readers use the current correction.
- **Alerts are code, not data.** Thresholds live in `thresholds.py`. They have a
  version and a citation. Postgres triggers enforce what the form permits.
- **Conditions hide questions. They do not answer them.** Hidden is not N/A. The
  app keeps hidden answers and shows them in the “not shown” tray. They never
  print.
- **Frozen versions win.** Submitted and approved output comes from the version
  payload. Do not recalculate old output from current data. Do not relink a frozen
  review.
- **Do not add clinical arithmetic without evidence.** Do not infer parity, living
  children, diagnosis or cause. Do not suggest a cause.
- **Keep changes small.** Use focused commits. The test suite is large. Broad
  changes are easy to break.

## Conditional form

`conditions.py` controls visibility. An unanswered controller shows the question.
A definite excluded answer hides it. Unknown ANC answers use `WhenYes`. `unknown`
means uncertainty, not a definite no. A specification field is required when the
user selects its option, even if an upstream answer is unknown.

Do not add the retired `f4.delivery.neonatal_death_time` field. It was a misread
of the maternal post-birth bands. The active field is
`f4.delivery.post_birth_complication_time`. It is shown when
`f4.delivery.phase = post_birth`. Old answers stay in `LEGACY_FIELDS`. Do not map
them to the new field.

## Amendments

Only an approved review can change. An amendment is a private staged copy of the
approved answers (`ReviewItem.amendment` not null). It does not edit the live
review. A review can have one open amendment. Different reviews can each have
one.

- The review author opens or carries out an amendment. An FNO can request one.
  The FNO supplies the reason. The author submits. The FNO approves.
- No self-approval. The person who submits cannot approve.
- Submit needs at least one change. It runs the same checks on the staged
  answers. It creates no version.
- Approval runs the checks again. It creates
  `ReviewVersion(kind=amendment, amends_version=base)` and syncs the live items.
- The previous approved version stays official until approval. The pending output
  has a **DRAFT — NOT APPROVED** stamp.
- Conditions and checks read the amendment scope. The official review keeps its
  frozen `applies` flags.
- No new proposal rules run during an amendment. Legacy fields carry forward from
  the base payload. Do not reinterpret them.
- Use `review/scope.py` to read items. Do not use `review.items.all()`.

See `docs/amendments.md`.

## Provenance appendix

`review/provenance.py` freezes a source snapshot for each value. It does this at
submit and amendment submit. The format version is 1.

- Reused and derived values carry the accepted proposal inputs, rule and version.
- Entered and corrected values carry the entry decision. They do not get a fake
  source.
- N/A carries state, reason and decision.
- Amendments mark changed values and carry unchanged values from the base.
- The app checks `provenance_hash` at approval and output. A mismatch blocks
  approval.

Each field row has a **provenance** link. It opens a drawer with the source chain,
decision and change history. All roles can see it. The full appendix prints at
`/review/<pk>/output/#provenance`. A pending amendment has the same appendix at
`/review/<pk>/amend/<id>/output/#provenance`. Do not repeat the full appendix
under the workspace form. Old versions without a snapshot say so. They rebuild
only from the proposal record and mark it *reconstructed*. Do not read live
proposals for a version 1 provenance payload. See `docs/provenance.md`.

## Quick clinical review

`/quick` asks only the clinical-judgement fields plus the contributing-factors
checklist. Record values are accepted automatically on load.

An answered field belongs to whoever answered it. A clinician edit is an
override: it wins, the record candidate is closed silently, and the collapsed
section shows the clinician's value marked **overridden**. Do not create a
conflict prompt and do not block submission for a typed answer. Only a value
that came from a record is flagged when new evidence supersedes it.

## Checks

Checks run on Check or Submit. Only a required **clinical judgement** blocks the
author: registry-required fields, ERROR-severity conditional follow-ups and
their specification fields, filtered to `Field.is_clinician_only`. A missing
document value is advisory — it is a record gap for the FNO/records team, never a
reason to stop the clinician. Everything else is frozen with the version under
`checks` and shown to the FNO as **Checks at submission**. Submit asks for one
confirmation; advisory notices do not stop it. The resident note survives a
blocked submit. The checks version is in the frozen payload and the audit event.

The check groups include:

- required fields. N/A on a required question is an error.
- missing conditional follow-ups.
- reconsideration after changed evidence.
- current source records, source corrections and multiple current records.
- precision-aware impossible dates and late entries.
- review-value checks for age, counts, durations and ICU.
- interval, transfusion and neonatal consistency warnings.
- retained answers, late entries, missing summary and no labour record.

See `docs/checks.md`. Do not make every optional field a blocker.

## Brief status

Done:

- Labour records, add, view, corrections and history.
- Review linked to a source, with or without a labour record.
- Proposed reuse with provenance and derived calculations.
- Clinician accept, reject and correct. The source stays immutable.
- Conditional Form 4. It can resume. It has all 99 fields.
- No unsupported conclusions.
- Late entries are visible. Missing chart values are blank cells or dots. The
  chart lists recorded times. It does not apply a cadence gap rule or claim a
  guideline breach.
- Checks before submission.
- Roles, return with comments, approval and frozen versions.
- Structured output from versions.
- Amendments.
- Provenance appendix (version 1).
- Security basics.
- Integrity, confidentiality and DPDP controls with a gap register.
- Form 1 from the same review. It auto-fills from the patient registration,
  death and delivery records; only reporting/ANM details and death during
  delivery need entry. Form 1 stays live. Form 4 stays frozen.
- All four synthetic cases.

Remaining:

1. **Security gaps.** FNO facility scoping, MFA and login throttling, live-volume
   encryption, `verify-full` certificate checks, full access logs, scheduled
   off-host backups, breach tooling and retention. Do not claim these are solved.
   See `docs/security.md`.
2. **Demo script** and final limitations note.

## Uncertainties

- `discharged_at` is administrative closure. If it is after death, `timing.c`
  uses death as the clinical exit. This is an implementation choice, not a
  verified government rule.
- Estimated timestamps cannot establish order. A same-day date-only pair is
  uncertain. The app catches future date-only dates. It does not catch estimated
  future dates.
- Interval checks use a one-minute tolerance.
- Multiple current death or delivery records produce warnings. Checks use the
  latest clinical time as a fallback.
- The PDF does not settle stillbirth cause capture, referral-table availability
  or abortion anaesthesia. See `docs/conditions.md`.
- A review can have one open amendment. FNO comments on an amendment are overall,
  not per field. Proposal rules do not run again during an amendment. See
  `docs/amendments.md`.
- Residents see their own or assigned reviews. FNOs see all reviews. Facility
  scoping is not implemented because the app has no user-to-facility map. The
  app DB role is opt-in. The default connection is the owner. See
  `docs/security.md`.

## Reference documents

- `docs/setup.md`
- `docs/quick-sources.md`
- `docs/db-audit.md`
- `docs/design.md`
- `docs/amendments.md`
- `docs/provenance.md`
- `docs/form1.md`
- `docs/security.md`
- `docs/dpdp.md`
- `docs/conditions.md`
- `docs/checks.md`
- `docs/lcg-storage.md`
- `docs/evidence-map.md`
- `docs/dependencies.md`
- `docs/inventory.md`
- `docs/overlap.md`
- `docs/form4-source.txt`
- `TODO.md`
