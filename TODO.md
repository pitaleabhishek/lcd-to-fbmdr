# To-do

Living list for the seven-day build. Check things off here; do not keep a second
list. `[x]` done, `[ ]` open, `[~]` partial.

_Last updated: 6 November 2026. 135 tests passing. 96 Form 4 fields, 34 LCG variables._

## Built

- [x] LCG model: 7 sections, 34 variables, values reconciled to the chart, validation trigger
- [x] Form 4 model: 14 sections, 96 fields, three block schemas, validation trigger
- [x] Case 0 (complete labour) and Case A (death after charted labour, clinically coherent)
- [x] Labour record screen: form header, stage bands, birth marker, late-entry marking
- [x] Review workspace: section nav with counts, progress, Show remaining, autosave (250ms + flush), error-only field feedback
- [x] Blocks: referral (four places, keyed by place), diagnosis rows, interventions matrix — all autosaving
- [x] Inputs: enums as selects, multi as checkboxes, native date/time pickers, month/year selects, durations in d/h/m
- [x] Accept / reject / correct, revert last change, no-op saves that never flip origin
- [x] Proposals with a source drawer; every input line shows its time and original author and has **see source** opening the chart column or record, value highlighted; derived values name their calculation, and an accepted proposal keeps its inputs and calculation in the row
- [x] Alert crossings computed from immutable observations (`review/thresholds.py`, `lcg_2021@1`), shown as evidence on 5 Form 4 fields; map in `docs/evidence-map.md`
- [x] N/A toggles in place — reads "Not applicable", note and clear stay in position, no reload
- [x] Internal field keys hidden from the form; kept as tooltips and in JSON output
- [x] Submit → return with per-field comments → fix → resubmit → approve
- [x] FNO can update an open return; Approve blocked while comments exist; typed comments survive the refusal
- [x] Sticky return bar with previous/next navigation between commented fields
- [x] Commented fields highlighted for the resident; previously-returned fields stay highlighted for the FNO
- [x] Role separation: author-only editing, no self-approval, FNO comments/returns/approves
- [x] Versions and output (HTML + JSON) rendered from a version; resident handover note per version, never printed
- [x] Review history: versions, returns with per-field comments, paginated activity (100/page), per-field filter, 2-minute grouping
- [x] Dependency register (`docs/dependencies.md`)
- [x] Overlap inventory generated and reconciled to the PDF (96/96 labels)
- [x] Conditional Form 4: 2 whole-section gates and 30 field rules (`review/conditions.py`, `docs/conditions.md`); hidden fields keep earlier answers, FNO comments override, submitted versions freeze `applies`
- [x] Review creation: one form for an existing woman or a new death; one-click from a labour record; `Review.source_document` is explicit; reporting facilities can be typed in and are created if absent; a no-LCG review says so plainly
- [x] Checks before submission: deterministic missing/impossible/inconsistent rules (`review/checks.py`, `docs/checks.md`), plain-language panel shown only after Submit, inline messages, errors block, warnings need one confirmation

## Essential, open

- [x] **LCG entry form** — one compact panel on the labour record: variable, time,
  value, author, documented-at; stage stamped from the chart. Append-only.
- [x] **Corrections** — a new row superseding the old one, with a reason; the chart
  and alert rules read only the head of the chain, the original stays in history.
- [x] **History screen for the labour record** — who wrote what, when, late entries,
  supersessions; filterable by item and author, paginated.
- [ ] **Cases B, C, D** — caesarean after labour, no labour record, referred in after delivery
- [ ] **Amendments** — approved reviews frozen; needs an attributed amendment path
- [ ] **Overlap analysis write-up** — per Dr Atter's four categories: counts, sources, false friends, 1/96 finding
- [ ] **Security note** — and close the gaps it exposes: non-owner DB role, author/facility scoping, login throttling
- [ ] **Output provenance appendix** — "from where" per printed value

## Desirable

- [ ] Printable Form 4 — print stylesheet for the wet-signature item
- [ ] Timeline combining labour observations and later events, contemporaneous vs retrospective
- [ ] Explicit "no observation recorded" marker in gaps (Case A's two-hour hole has no signal)
- [ ] Form 1 back-fill from the review
- [ ] Two hospitals / facility scoping
- [ ] Collapse consecutive edits in history beyond the current 2-minute grouping

## Deliverables

- [ ] Overlap document exported alongside the app (`docs/overlap.md`)
- [ ] Demo script
- [ ] Final security/limitations note

## Out of scope (do not build)

LCG charting and plotting · MPCDSR/HMIS/ABDM integrations · death certificates ·
committee module · offline sync · AI narratives or suggested causes · production
deployment or compliance certification · partograph adapter (seam only).
