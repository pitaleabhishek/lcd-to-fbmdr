# To-do

Living list for the seven-day build. Check things off here; do not keep a second
list. `[x]` done, `[ ]` open, `[~]` partial.

_Last updated: 5 November 2026._

## Built

- [x] LCG model: 7 sections, 34 variables, values reconciled to the chart, validation trigger
- [x] Form 4 model: 14 sections, 96 fields, three block schemas, validation trigger
- [x] Case 0 (complete labour) and Case A (death after charted labour)
- [x] Labour record screen, form-style header, stage bands, late-entry marking
- [x] Review workspace: sections, counts, proposals with provenance drawer, autosave
- [x] Blocks: referral (four places), diagnosis rows, interventions matrix
- [x] Applies to all inputs: enums as selects, multi as checkboxes, dates as pickers, durations in d/h/m
- [x] Submit → return with per-field comments → fix → resubmit → approve
- [x] Role separation: author vs FNO, no self-approval, author-only editing
- [x] Versions, output (HTML + JSON) from a version
- [x] History screen for the review (versions, returns, activity), visible to resident and FNO
- [x] Dependency register (`docs/dependencies.md`)
- [x] Overlap inventory generated and reconciled to the PDF (96/96 labels)

## Essential, open

- [ ] **Cases B, C, D** — caesarean after labour, no labour record, referred in after delivery
- [ ] **Alert crossings as evidence** — `thresholds.py`, computed not stored, shown beside the field
- [ ] **History screen for the labour record** — same shape as the review history
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
- [ ] HTMX for the provenance drawer and section counts (currently plain fetch)

## Deliverables

- [ ] Demo script
- [ ] Final security/limitations note
- [ ] Dependency register kept current when a package is added
- [ ] Overlap document exported alongside the app

## Out of scope (do not build)

LCG charting and plotting · MPCDSR/HMIS/ABDM integrations · death certificates ·
committee module · offline sync · AI narratives or suggested causes · production
deployment or compliance certification · partograph adapter (seam only).
