# To-do

Living list for the seven-day build. Check things off here; do not keep a second
list. `[x]` done, `[ ]` open, `[~]` partial.

_Last updated: 5 November 2026. 77 tests passing._

## Next

- [ ] **History screen for the labour record** — same shape as the review history:
  who wrote what, when, late entries, supersessions. Then alert evidence.

## Built

- [x] LCG model: 7 sections, 34 variables, values reconciled to the chart, validation trigger
- [x] Form 4 model: 14 sections, 96 fields, three block schemas, validation trigger
- [x] Case 0 (complete labour) and Case A (death after charted labour, clinically coherent)
- [x] Labour record screen: form header, stage bands, birth marker, late-entry marking
- [x] Review workspace: section nav with counts, progress, Show remaining, autosave (250ms + flush), error-only field feedback
- [x] Blocks: referral (four places, keyed by place), diagnosis rows, interventions matrix — all autosaving
- [x] Inputs: enums as selects, multi as checkboxes, native date/time pickers, month/year selects, durations in d/h/m
- [x] Proposals with a provenance drawer; each input opens the source column/record with the value highlighted
- [x] Accept / reject / correct, revert last change, no-op saves that never flip origin
- [x] Submit → return with per-field comments → fix → resubmit → approve
- [x] FNO can update an open return; Approve blocked while comments exist; typed comments survive the refusal
- [x] Sticky return bar with previous/next navigation between commented fields
- [x] Commented fields highlighted for the resident; previously-returned fields stay highlighted for the FNO, without a summary strip
- [x] Role separation: author-only editing, no self-approval, FNO comments/returns/approves
- [x] Versions and output (HTML + JSON) rendered from a version; resident handover note per version, never printed
- [x] History screen for the review: versions, returns with per-field comments, paginated activity, per-field filter
- [x] Dependency register (`docs/dependencies.md`)
- [x] Overlap inventory generated and reconciled to the PDF (96/96 labels)

## Essential, open

- [ ] **Cases B, C, D** — caesarean after labour, no labour record, referred in after delivery
- [ ] **Alert crossings as evidence** — `thresholds.py`, computed not stored, shown beside the field
- [ ] **History screen for the labour record** — see Next
- [ ] **Amendments** — approved reviews frozen; needs an attributed amendment path
- [ ] **Conditional form** — honour `applicability` (abortion branches, transfusion units, neonatal cause)
- [ ] **Pre-submission checks** — plain-language inconsistencies, not just missing required fields
- [ ] **Overlap analysis write-up** — the document, not the CSV: categories, false friends, 1/96 finding
- [ ] **Security note** — and close the gaps it exposes: non-owner DB role, author/facility scoping, login throttling
- [ ] **Output provenance appendix** — "from where" per printed value

## Desirable

- [ ] Printable Form 4 — print stylesheet for the wet-signature item
- [ ] Timeline combining labour observations and later events, contemporaneous vs retrospective
- [ ] Explicit "no observation recorded" marker in gaps
- [ ] Form 1 back-fill from the review
- [ ] Two hospitals / facility scoping
- [ ] Collapse consecutive edits in history beyond the current 2-minute grouping

## Deliverables

- [ ] Demo script
- [ ] Final security/limitations note
- [ ] Overlap document exported alongside the app

## Out of scope (do not build)

LCG charting and plotting · MPCDSR/HMIS/ABDM integrations · death certificates ·
committee module · offline sync · AI narratives or suggested causes · production
deployment or compliance certification · partograph adapter (seam only).
