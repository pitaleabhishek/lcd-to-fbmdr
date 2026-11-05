# MDR Reuse — Technical Design

**Prototype for a 7-day assignment.** Reuse labour documentation in a Facility-Based Maternal Death Review (Form 4), with provenance: nothing re-keyed, nothing claimed that wasn't recorded.

Status: design, not implemented. Date: 4 November 2026.

---

## 1. Scope

**In:** LCG-shaped labour records; the death; a review with or without a labour record; proposed reuse with provenance; accept/reject/correct; the rest of Form 4; gaps and late entries visible; pre-submission checks; resident → FNO return/approve; locked reviews with attributed amendments; Form 4 output with per-value origin.

**Out:** LCG charting, MPCDSR/HMIS/ABDM integration, death certificates, committee module, offline sync, AI narratives, production deployment, FHIR, OCR, multi-tenancy.

---

## 2. Data model

Domain tables hold **what was recorded**. The review holds **what the clinician asserts**. A proposal is the bridge. A version is what gets printed.

A Form 4 answer is never read live from a domain table. This is what makes the referral-after-delivery case work: the delivery belongs to the pregnancy at its own facility, the admission belongs to the receiving hospital, and the printed interval is N/A with a reason rather than a negative number.

`?` = nullable.

```
Facility(id, name, level, district, address, nodal_name, nodal_phone)
Patient(id, mcts_no, name, age, sex, address, education, bpl, phone)
Pregnancy(id, patient, outcome, outcome_at, gestation_weeks, gestation_days,
          risk_codes jsonb, risk_note, anc_received, anc_facility_type,
          anc_provider, anc_counselled, anc_risks, abortion_detail jsonb,
          postnatal_course, postnatal_note)
Admission(id, pregnancy, facility, uin, admitted_at?, time_precision,
          discharged_at, admitted_by, medico_legal, condition_on_admission,
          complaints)
SourceDocument(id, pregnancy, admission?, kind, source_format, origin_facility,
          author, entered_by, documented_at, received_at, entered_at,
          time_precision, supersedes_id, note)
  kind: lcg | partograph | admission_note | referral_slip | anc_card | death_summary
Observation(id, document, kind, value_num, value_text, value_code, unit,
          observed_at?, observed_at_precision, documented_at?, entered_at,
          entered_by, author, author_role, raw_label, raw_value,
          supersedes_id, note)
CareContact(id, pregnancy, sequence, place_type, facility_name, date, onset_at,
          transport, time_to_reach, money_transport, attended_by,
          reason_for_referral, referral_slip, treatment_given, money_treatment,
          time_in_facility, supersedes_id)
AdmissionDiagnosis(id, admission, code, underlying_cause, note)
Delivery(id, pregnancy, delivered_at?, time_precision, mode, facility,
          performed_by, supersedes_id, note)
Neonate(id, delivery, outcome, assessed_at, status_context, cause, note)
IcuStay(id, admission, from_at?, from_precision, to_at, to_precision, note)
Transfusion(id, admission, at, component, units, reaction, note)
Intervention(id, admission, phase, kind, at, note)
Death(id, pregnancy, admission?, died_at?, time_precision, place, brought_dead,
          certified_by, supersedes_id)

Review(id, pregnancy, reporting_facility, reporting_admission?, status,
          current_version, edit_revision, created_by, assigned_to?, created_at,
          submitted_by, submitted_at, returned_by, returned_at, return_comment,
          approved_by, approved_at, deadline_at?)
  status: draft | submitted | returned | approved | voided
ReviewVersion(id, review, version_no, kind, payload_json, payload_hash,
          created_by, created_at, amends_version_id?, submission_version_id?,
          registry_version, output_template_version)
  kind: submission | approval | amendment
ReviewItem(id, review, field_key, answer_state, value_json, origin, reason,
          applicability_state, decided_by, decided_at,
          accepted_proposal_id?, needs_reconsideration)
  UNIQUE(review, field_key)
  answer_state: unanswered | answered | not_known
  applicability_state: applicable | not_applicable | undetermined
  origin: reused | derived | entered | corrected | none
Proposal(id, review, field_key, rule_key, rule_version, source_kind,
          value_json, frozen_inputs jsonb, input_hash, created_at, status,
          status_reason)
  status: proposed | accepted | rejected | superseded | stale
ProposalDecision(id, proposal, decision, by, at, reason)
Amendment(id, review, base_version_id, payload_json, reason, by, at, status,
          decided_by, decided_at, return_comment)
  status: draft | proposed | returned | approved
AuditEvent(id, at, actor, action, entity_type, entity_id, review, payload jsonb)
```

Recorded facts are append-only, corrected by a new row with `supersedes_id` (no cycles, no branches): `Observation`, `SourceDocument`, `Delivery`, `Death`, `CareContact`. Everything else is editable, and every change writes an `AuditEvent`.

**The source side is registered too.** The LCG is not a free-text stream: seven printed sections and 34 variables are declared with their order, type, unit and ALERT rule (`review/registry_lcg.py`), and every `Observation` points at one of them. The alert column is a rule, never a cell. Each observation carries its stage (`first` or `second`) on the row, stamped when it is written; the rows are append-only, so a cell cannot change stage later, and a test asserts that one time column never mixes stages. There is no column entity: the LCG's time axis is blank on the paper form, so columns are derived by grouping observations on time, and a missed observation is found by comparing that grouping against the cadence a rule set requires. Two views render the result: `lcg_chart` (one row per variable, cells across time) and `lcg_cells` (one row per cell, with computed column and stage). A `Proposal` freezes its inputs and rule version; decisions are new rows, never edits. `edit_revision` counts workspace edits, `version_no` counts published versions.

**Rules that prevent silent data loss**

- N/A has one decider: `applicability_state`. There is no `answer_state = not_applicable`.
- Rejecting a proposal never clears an answer. Rejection on an unanswered field leaves it unanswered; rejection of one candidate on an answered field leaves the answer untouched.
- The WHO 42-day window is a computed classification rule, not a constraint, and applies to abortion and ectopic outcomes too.

---

## 3. Fields and blocks

Every position on the printed Form 4 is one **answer slot**.

- **Field** — one answer, one `ReviewItem`. Example: `f4.timing.e`, the admission → delivery interval.
- **Block** — a repeating group (referral, neonatal, transfusion, interventions) is **one** `ReviewItem`; its `value_json` is a schema-validated list of rows.
- **Block field** — one cell in one row, addressed `field_key#row_index`. It is never its own `ReviewItem`. Each row carries its own `origin`, `reason` and `accepted_proposal_id`; the block's `origin` is a roll-up, `mixed` when rows differ.
- Accept and reject apply to the whole block, so a block proposal always carries the full list.

One representation per block. Never a second editable copy in a child table.

**Keys.** `f4.<section_key>.<label>` — `f4.timing.e`, `f4.antenatal_care.a`. The section key, never the printed number: the form repeats numbers 1–4 then 2–10, and printed 2, 3 and 4 each split across two sections. Rule keys derive from field keys, so the grammar is fixed before the inventory is generated.

---

## 4. Form 4 map

| Key | Section | Source facts |
|---|---|---|
| `background` | Background | Facility, Patient, Admission.uin |
| `timing` | 1.a–1.g | Admission, Death, IcuStay, Delivery |
| `admission` | 2. On admission | Observation, Admission.complaints |
| `condition` | 3. Condition + referral block | CareContact, AdmissionDiagnosis |
| `diagnosis` | 4. Diagnosis at admission | AdmissionDiagnosis |
| `abortion` | 2. Abortion | Pregnancy.abortion_detail |
| `antenatal_care` | 3. ANC | Pregnancy.anc_* |
| `delivery` | 4. Delivery, puerperium, neonatal | Delivery, Neonate(n), Pregnancy.postnatal_* |
| `interventions` | 5. Interventions | Intervention, Transfusion(n) |
| `primary_diagnosis` | 6. Primary diagnosis | none — judgement |
| `cause_of_death` | 7. Cause of death | none — judgement |
| `factors` | 8. Factors present | none — judgement |
| `autopsy` | 9. Autopsy | Observation |
| `summary` | 10. Case summary | none |

The field inventory is **generated from the registry**, not hand-written, and reconciled page by page against the extracted Form 4 text (`docs/form4-source.txt`). The first slice — 53 fields — is registered; remaining sections and block schemas are added as they are built. Every field carries an overlap category, a source, a relationship, a one-sentence rationale, and terminology or precision notes where they differ — that is the overlap document, one row per field.

---

## 5. Reuse

```python
Field(key="f4.timing.e", section="timing",
      label_printed="e. Admission – delivery interval",
      type="duration", handling="derive",   # propose | derive | prompt | manual | evidence
      applicability="delivered",
      rule="f4.timing.e.admission_delivery_interval")
```

A rule returns a value plus its inputs, or a refusal:

- `NotComputable("no delivery recorded", state="missing")`
- `NotComputable("admission time unknown", state="unknown")`
- `NotComputable("delivered before admission here", state="not_applicable")`

None of them completes a field, and a proposed N/A still needs clinician confirmation. Date-only and estimated values stay at their precision — no midnight, no invented duration.

**False friends.** The prohibition attaches to the edge, not the field. Barred from `propose`: active-labour diagnosis→admission · "partograph used"→LCG exists · lag alert→prolonged labour · BP/P++→eclampsia · oxytocin/IV fluids→interventions · plan text→case summary · fetal monitoring→neonatal outcome · LCG risk factors→"told antenatally" · no birth recorded→undelivered · last observation→time of death · condition on admission→first observation · LCG duration→hospital stay · onset of labour→active-labour diagnosis · position OP→abnormal presentation.

Parity may populate `Para` but not Gravida, Abortions or Living children.

**Thresholds** belong to a named, versioned rule set citing its guideline. LCG and partograph have different action lines and assessment frequencies, so a rule set only runs on the format it was written for. Anything computed after the fact is labelled *computed evidence*, separate from a documented alert.

---

## 6. Staleness

Any relevant source change triggers `reevaluate(pregnancy)`, synchronously. Per field, a candidate appeared, changed, or is no longer computable.

- Editable answers: mark `needs_reconsideration`, keep the old proposals, block submission until resolved.
- Submitted or approved content: never mutate. Write a discrepancy event; approval stays blocked until an FNO disposes of it in writing.
- Accepted values are never silently replaced.
- Multiple candidates are shown together in a deterministic order; the clinician chooses. No ranking.

---

## 7. Validation

Blocking: internally inconsistent typed value (e.g. diastolic ≥ systolic); `outcome=undelivered` together with a `Delivery`; required field empty at submit; unresolved `needs_reconsideration`.

Warning, allowed: death earlier than admission when times are exact.

Informational: "supporting observations not recorded" — never "inconsistent".

A required field may be answered "unknown" with a reason. The system does not force unavailable clinical facts to be invented. A historical observation is never edited; it is flagged and needs explicit disposition.

---

## 8. Workflow

```
draft ──submit──> submitted ──return──> returned ──submit──> submitted ──approve──> approved
                                                                                    │
                                                            amend ──────────────────┘
```

Resident authors; FNO returns with a comment or approves. No self-approval. Amendments need FNO approval, and the previous approved version stays official until then. `deadline_at = death + 24h` only when the death time is exact, otherwise shown as uncertain. Late submission is flagged, never blocked. Drafts are never deleted.

---

## 9. Output

Printable HTML in Form 4 layout with printed labels. Every value is marked `R` reused, `D` derived, `E` entered, `C` corrected, `—` none, with a provenance appendix: source document, observed / documented / entered times, author, entering user, accepted by, rule and version.

`entered_at` is server-assigned and cannot be backdated. `author` is who wrote the source; `entered_by` is who typed it.

Output renders from a `ReviewVersion` and its recorded registry and template versions, so historical output stays reproducible. A pending amendment renders from the amendment payload against the base version's template, stamped **DRAFT — NOT APPROVED**.

---

## 10. Build order

| Day | Work |
|---|---|
| 1 | Models, migrations, triggers, registry, key grammar, **case A end to end**; inventory reconciled against the PDF |
| 2 | Case list, labour timeline, entry form, auth, object permissions |
| 3 | Rules, proposals, accept/reject/correct, provenance drawer, reconsideration |
| 4 | Remaining sections and blocks; applicability; autosave |
| 5 | Return/approve, lock, amendment workspace, history |
| 6 | Cases B, C and D; staleness and conflict; Form 4 print + JSON |
| 7 | Overlap document with rationale and notes; dependency register; security note; tests; demo |

All four cases complete the full workflow before any stretch item is touched.

---

## 11. Security and confidentiality

- Server-side object permissions on every view, not only the review. A resident reaches reviews they authored or are assigned; an FNO reaches their facility.
- No self-approval, for reviews or amendments.
- CSRF on every state change; no state-changing GET; secure cookies; login throttling.
- One transaction per transition with `edit_revision` checked; stale writes rejected.
- The app connects as a non-owner DB role, so append-only triggers are real.
- Audit payloads minimal; no patient payloads in logs.
- Fictional data only. **No claim of DPDP compliance** — backups, retention, consent and breach procedure are stated gaps.

---

## 12. Cases

| Case | Content | Demonstrates |
|---|---|---|
| A | LCG, alert crossing, one missed observation, two authors, late entry, vaginal delivery, PPH death | core journey, staleness, three timestamps |
| B | Cervical lag → caesarean → sepsis at 48 h | caesarean after labour, two ICU stays, per-component transfusion |
| C | No labour record, died undelivered at 34 weeks | N/A with reason, unknown applicability |
| D | Delivered at PHC 17:40, referral slip, admitted DH 22:10, died 09:40 | negative interval, external source, conflict, indeterminate ordering |

Fictional identities, fixed clinical dates, deterministic seeds. No fixture asserts a diagnosis the record does not support — gaps stay gaps.

---

## 13. Open questions

1. The brief's four overlap categories — that document was not supplied.
2. May admission, patient and referral records provide reusable values, with LCG-only overlap distinguished?
3. How should "partograph used" represent an LCG? Proposed: keep instrument identity, require an explicit answer, never auto-convert.
4. For ambiguous gestation and time boundaries, may we document our interpretation while preserving the exact source value?

Defaults: only supplied external information is used; uncertainties stay unknown; late submission is flagged, not blocked.
