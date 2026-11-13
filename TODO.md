# Task list

This is the only task list. Do not keep a second list.

`[x]` done. `[ ]` open. `[~]` partial.

Last update: 13 November 2026. 275 tests pass. The app has 99 Form 4 fields and
34 LCG variables.

## Built

- [x] LCG model: 7 sections, 34 variables, chart reconciliation and a validation
  trigger.
- [x] Form 4 model: 14 sections, 99 fields, three block schemas and a validation
  trigger.
- [x] Case 0 (complete labour) and Case A (death after charted labour).
- [x] Labour record screen: header, stage bands, birth marker and late-entry mark.
- [x] Review workspace: section nav, counts, progress, Show remaining, autosave
  and field errors.
- [x] Blocks: referral (four places), diagnosis rows and intervention matrix. All
  blocks autosave.
- [x] Inputs: selects, checkboxes, date and time pickers, month and year selects,
  and durations.
- [x] Accept, reject and correct. A no-op save does not change origin. No undo
  button.
- [x] Proposals with a source drawer. Each input shows its time and author. **See
  source** opens the chart column or record. Derived values show the calculation.
- [x] Alert crossings from immutable observations (`lcg_2021@1`). They show as
  evidence on five Form 4 fields. See `docs/evidence-map.md`.
- [x] N/A toggle in place. It shows “Not applicable”. The note and clear controls
  stay in place. No reload.
- [x] Internal keys are hidden from the form. They stay as tooltips and in JSON.
- [x] Submit, return with comments, fix, resubmit and approve.
- [x] FNO can update an open return. Approve is blocked while comments exist.
  Typed comments survive the refusal.
- [x] Sticky return bar with previous and next navigation.
- [x] Commented fields stay marked for the resident and the FNO.
- [x] Role separation: author edits, FNO returns and approves, no self-approval.
- [x] Versions and output (HTML and JSON) from a version. Handover note per
  version. The note never prints.
- [x] Review history: versions, returns, comments, paged activity, field filter
  and two-minute grouping.
- [x] Dependency register (`docs/dependencies.md`).
- [x] Overlap inventory from the PDF. All 99 labels match.
- [x] Conditional Form 4 (version 2). It includes post-birth maternal timing, ANC
  risks, specification fields, referral table, abortion anaesthesia and legacy
  answers. Hidden fields keep old answers. FNO comments force a field into view.
  Frozen versions keep `applies`.
- [x] Review creation: one form for an existing woman or a new death. One click
  from a labour record. `Review.source_document` is explicit. The app creates a
  new facility when needed. A review without an LCG says so.
- [x] Checks before submission (version 3). Only a required clinical judgement
  blocks the author. Every other finding is frozen with the version and shown to
  the FNO. The author sees a plain confirmation.
- [x] One-command setup: `start.sh`, `start.ps1`, `demo_setup` and `docs/setup.md`.
- [x] Optional shared HTTP Basic auth for a hosted demo.
- [x] Database audit: removed 4 unused review tables; 32 tables remain (`docs/db-audit.md`).
- [x] Integrity, confidentiality and DPDP answer. See `docs/dpdp.md` and
  `docs/security.md`.
- [x] Quick clinical review fed from records: 99 fields mapped to eight documents.
  76 are document-sourced; 44 are wired and accepted automatically. The page asks
  ten judgement questions plus the 13-factor checklist. See
  `docs/quick-sources.md`.
- [x] Clinician edits override record values. The record candidate is closed
  silently and the collapsed section marks the value **overridden**.
- [x] GPLA: parity from the LCG header; gravida, abortions and living children
  from the ANC card on the pregnancy. Labour record no longer claims delivery
  facts.
- [x] Submit asks for one confirmation. Only a required clinical judgement blocks
  the author; advisory checks are frozen and shown to the FNO.

## Essential, open

- [x] **LCG entry form**: one panel on the labour record. It records variable,
  time, value, author and documented-at. The chart stamps the stage. Append-only.
- [x] **Corrections**: a new row replaces the old row. A reason is required. The
  chart and alerts use the current row. The original stays in history.
- [x] **Labour history screen**: shows who wrote what and when. It includes late
  entries and corrections. It filters by item and author. It is paged.
- [x] **Happy-case seed**: clean LCG, one alert crossing, no gaps or late entries.
  It has a complete draft, zero checks, 100% resolved, and a full
  submit/return/resubmit/approve/amendment cycle.
- [x] **Cases B, C and D**: caesarean after labour, no labour record, and referral
  in after delivery. Case D is a complete draft.
- [x] **Amendments**: an approved review is closed. A resident opens an attributed
  amendment. An FNO can request one. Submit runs the checks. Approval creates a
  new `ReviewVersion(kind=amendment)`. The old version stays official until
  approval. One open amendment per review.
- [x] **Overlap analysis**: all 99 fields in Dr Atter's four categories, with
  sources, false friends, terminology, precision and the 1/99 finding. See
  `docs/overlap.md`.
- [~] **Security basics**: headers, cookies, password validators, review scoping,
  least-privilege Postgres role, Caddy TLS, Postgres TLS with SCRAM and encrypted
  backups. See `docs/security.md`. Remaining: FNO facility scoping, MFA and login
  throttling, live-volume encryption, `verify-full`, full access logs, scheduled
  off-host backups, breach tooling and retention.
- [x] **Output provenance**: per-value snapshot (version 1) at submit and amendment
  submit. The app checks it at approval. The drawer shows it per field. It prints
  at `/review/<pk>/output/#provenance`.

## Desirable

- [x] Printable Form 4 for wet signature. Only the current approved version can
  print. The print copy has tick boxes, block tables, blank lines and the
  signature block. It has no origin chips or provenance. See
  `docs/form4-print.md`.
- [ ] Timeline that combines labour observations and later events.
- [x] Missing observations show as blank cells or dots. The chart lists recorded
  times and the birth marker. It does not use a cadence gap rule.
- [x] Form 1 from the review. Shared facts are reused. Form 1 fields are
  entered once. Form 1 stays live and editable. See `docs/form1.md`.
- [ ] Two hospitals and facility scoping.
- [ ] Collapse consecutive history edits beyond two minutes.

## Deliverables

- [x] Overlap document (`docs/overlap.md`).
- [x] Hosted demo at `https://lcgtofbmdr.nirovia.in` through a separate named Cloudflare tunnel.
- [ ] Demo script.
- [ ] Final security and limitations note.

## Out of scope

Do not build:

- LCG charting or plotting.
- MPCDSR, HMIS or ABDM integration.
- Death certificates.
- Committee module.
- Offline sync.
- AI narratives or suggested causes.
- Production deployment or compliance certification.
- Partograph adapter. Keep the seam only.
