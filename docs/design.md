# MDR Reuse — Technical Design v3

**Prototype for a 7-day assignment.** Reuse labour documentation in a Facility-Based Maternal Death Review (Form 4) with full provenance. Nothing re-keyed; nothing claimed that wasn't recorded.

Status: design, not implemented.
Supersedes v2 after the Codex review of 3 November 2026. Section 21 lists what was accepted, amended and rejected; Section 22 records the consistency pass that followed.
Date: 3 November 2026.

---

## 0. How to read this

- **[R]** = assignment requirement.
- **[D]** = our design decision, made to fit seven days.
- **[?]** = unresolved, needs confirmation.
- **[L]** = known limitation, stated rather than hidden.

**Abbreviations.** LCG — WHO Labour Care Guide · FBMDR — Facility-Based Maternal Death Review · FNO — Facility Nodal Officer · MO — Medical Officer · MCTS — Mother and Child Tracking System identifier · UIN — inpatient unique number · G/P/A/L — gravida / para / abortions / living children · ANC — antenatal care · PPH — postpartum haemorrhage · APH — antepartum haemorrhage · PRBC / FFP — packed red blood cells / fresh frozen plasma · ICU — intensive care unit · DPDP — Digital Personal Data Protection Act, 2023 · HMIS, MPCDSR, ABDM — government health information systems, integration out of scope · FHIR — Fast Healthcare Interoperability Resources · LTS — long-term support.

---

## 1. Scope

**[R] In:** LCG-shaped labour records; death event; review with or without a labour record; proposed reuse with provenance; accept/reject/correct; the rest of Form 4 conditionally; gaps and late entries visible; pre-submission checks; resident→FNO return/approve; locked reviews with attributed amendments; Form 4-structured output with per-value origin; history; four synthetic cases.

**[R] Out:** LCG charting/plotting, MPCDSR/HMIS/ABDM integration, death certificates, committee module, offline sync, AI narratives, production deployment.

**[D] Out:** multi-tenancy, FHIR server, document ingestion/OCR, partograph adapter (seam only), general-purpose form engine, amendment round-trip beyond one return.

---

## 2. Vocabulary

- **[D]** `Pregnancy` — one pregnancy from conception to its outcome (delivery, abortion, ectopic, or death undelivered).
- **[D]** `Admission` — one stay at one facility, with its own inpatient number, admission and discharge times.
- **[D]** `Review` — the Form 4 investigation. It is attached to a `Pregnancy`, a **reporting facility**, and an **optional reporting admission or presentation**. The admission is optional because a woman may be brought in dead, with no admission record.
- **[D] Source fact** — something recorded about the woman or the pregnancy: an observation, a delivery, a death, an admission detail. Stored in domain tables. Recorded events (observations, documents, deliveries, deaths, contacts) are append-only; person and encounter attributes (patient, pregnancy, admission) are editable but audited — see Section 4. Either way, a source fact is not a review answer.
- **[D] Review answer** — what the clinician asserts Form 4 says. Stored only in `ReviewItem`, and only ever rendered from a `ReviewVersion`.
- **[D] Field** — one answer position on the printed Form 4, declared once in the registry. A single-valued field is one `ReviewItem`. A field inside a repeating block is a **block field**, addressed `field_key#row_index`; it is one row in the block's `value_json`, never a separate `ReviewItem`.
- **[D] Entry** — one instance of a block field, i.e. one row. **Answer slot** — the single place a field's answer lives: its own `ReviewItem`, or its row inside a block item.
- **[D]** The WHO 42-day window is a **classification rule** computed from `Pregnancy.outcome_at`, not a database constraint, and it applies to abortion and ectopic outcomes as well as delivery. Falling inside 42 days does not by itself establish a maternal-death classification.

**The spine of this design:** domain tables hold what was recorded; the review holds what the clinician asserts; a proposal is the bridge; a version is what gets printed. A Form 4 answer is never read live from a domain table.

This split is what makes the referral-after-delivery case representable: the delivery belongs to the pregnancy with its own facility; the admission belongs to the receiving hospital. The printed interval is then N/A with a reason, not a negative number.

---

## 3. Data model

```
Facility(id, name, level, district, address, nodal_name, nodal_phone)

Patient(id, mcts_no, name, age, sex, address, education, bpl, phone)

Pregnancy(id, patient, outcome, outcome_at, gestation_weeks, gestation_days,
          risk_codes jsonb, risk_note,
          anc_received, anc_facility_type, anc_provider, anc_counselled, anc_risks,
          abortion_detail jsonb, postnatal_course, postnatal_note)

Admission(id, pregnancy, facility, uin,
          admitted_at nullable, time_precision, discharged_at,
          admitted_by, medico_legal, condition_on_admission, complaints)

SourceDocument(id, pregnancy, admission nullable, kind, source_format,
               origin_facility, author, entered_by,
               documented_at, received_at, entered_at,
               time_precision, supersedes_id, note)
  kind: lcg | partograph | admission_note | referral_slip | anc_card | death_summary
  source_format: lcg_2020 | partograph_who | local_x
  time_precision: exact | estimated | date_only | unknown

Observation(id, document, kind, value_num, value_text, value_code, unit,
            observed_at nullable, observed_at_precision,
            documented_at nullable, entered_at, entered_by,
            author, author_role, raw_label, raw_value,
            supersedes_id, note)

CareContact(id, pregnancy, sequence, place_type, facility_name,
            date, onset_at, transport, time_to_reach, money_transport,
            attended_by, reason_for_referral, referral_slip,
            treatment_given, money_treatment, time_in_facility, supersedes_id)

AdmissionDiagnosis(id, admission, code, underlying_cause, note)

Delivery(id, pregnancy, delivered_at nullable, time_precision, mode,
         facility, performed_by, supersedes_id, note)

Neonate(id, delivery, outcome, assessed_at, status_context, cause, note)
  -- one row per baby; outcome may change, so it carries its own time/status

IcuStay(id, admission, from_at nullable, from_precision,
        to_at nullable, to_precision, note)
  -- a list, because a woman may go to ICU more than once

Transfusion(id, admission, at, component, units, reaction, note)
  -- one row per component (PRBC / FFP / platelets), never one shared "units"

Intervention(id, admission, phase, kind, at, note)   -- Form 4 Section 5 matrix rows

Death(id, pregnancy, admission nullable, died_at nullable, time_precision,
      place, brought_dead, certified_by, supersedes_id)

Review(id, pregnancy, reporting_facility, reporting_admission nullable,
       status, current_version, edit_revision, created_by, assigned_to nullable,
       created_at, submitted_by, submitted_at,
       returned_by, returned_at, return_comment,
       approved_by, approved_at, deadline_at nullable)
  status: draft | submitted | returned | approved | voided

ReviewVersion(id, review, version_no, kind, payload_json, payload_hash,
              created_by, created_at, amends_version_id nullable,
              submission_version_id nullable,
              registry_version, output_template_version)
  kind: submission | approval | amendment

ReviewItem(id, review, field_key, answer_state, value_json, origin, reason,
           applicability_state, decided_by, decided_at,
           accepted_proposal_id nullable, needs_reconsideration)
  UNIQUE(review, field_key)
  answer_state: unanswered | answered | not_known
  applicability_state: applicable | not_applicable | undetermined
  origin: reused | derived | entered | corrected | none

Proposal(id, review, field_key, rule_key, rule_version, source_kind,
         value_json, frozen_inputs jsonb, input_hash,
         created_at, status, status_reason)
  status: proposed | accepted | rejected | superseded | stale

ProposalDecision(id, proposal, decision, by, at, reason)

Amendment(id, review, base_version_id, payload_json, reason,
          by, at, status, decided_by, decided_at, return_comment)
  status: draft | proposed | returned | approved

AuditEvent(id, at, actor, action, entity_type, entity_id, review, payload jsonb)
```

**Answers versus sources.** Every field on the printed Form 4 has exactly one answer slot. A single-valued field is one `ReviewItem`. A repeating block (referral places, interventions, neonatal outcomes) is itself **one** `ReviewItem` whose `value_json` is a list of schema-validated rows; a block field is addressed as `field_key#row_index` and never becomes a separate `ReviewItem` row. Each row carries its own `origin`, `reason` and `accepted_proposal_id`; the block item's `origin` is a roll-up, `mixed` when its rows differ. Accept and reject apply to the whole block, so a proposal for a block always carries the complete list. Domain tables above are *source facts* that feed proposals; they are never the rendered answer. A clinician who types something with no source document creates an attributed review answer, not a fabricated observation.

**Answer state versus proposal state.** `ReviewItem.answer_state` is the answer; `Proposal.status` is the candidate. Two cases must not be confused: rejecting a proposal on an **unanswered** field records a `ProposalDecision` and leaves the field `unanswered`; rejecting one candidate on an **already answered** field records the decision and leaves the answer untouched. "Rejected" never masquerades as complete, and rejection never clears an answer. `accepted_proposal_id` points at exactly what was shown when accepted — the link survives the proposal being superseded.

**N/A has one decider.** `applicability_state` decides whether a field applies; `answer_state` only records the answer to an applicable field. There is no `answer_state = not_applicable`. A proposed N/A sets `applicability_state` and still requires clinician confirmation (Section 6).

**Server-assigned fields.** `entered_at` is set by the server at write time and cannot be supplied or backdated by a client. `author` is the person who wrote the source; `entered_by` is the user who typed it. Transcription by another user never transfers authorship, and an external document typed after the death may still have been written before it.

**Submission-ready** means: `answer_state != unanswered`, applicability resolved, field-specific requiredness satisfied, no blocking validation, and `needs_reconsideration` false. "Unknown" and "N/A" are separate states with separate reasons; neither is a generic escape hatch.

**Repeating blocks** use one representation only: the list inside the block's `ReviewItem`, validated against the block schema declared in the registry. There is never a second editable copy in a child table. A block edited during a draft produces an `AuditEvent` and bumps `edit_revision` like any other field.

---

## 4. Versioning and immutability

**[D]**

| Object | Rule |
|---|---|
| `Observation`, `SourceDocument`, `Delivery`, `Death`, `CareContact` | recorded facts, append-only; Postgres `BEFORE UPDATE OR DELETE` trigger raises |
| Corrections to a recorded fact | new row with `supersedes_id`; prior row retained. Supersession stays within one logical fact and one pregnancy, cannot cycle or branch, and the current row is selected explicitly |
| `ReviewVersion`, `ProposalDecision`, `AuditEvent` | append-only, and never corrected. A later version, decision or event supersedes by existing, not by editing |
| `Patient`, `Pregnancy`, `Admission`, `AdmissionDiagnosis`, `Neonate`, `IcuStay`, `Transfusion`, `Intervention` | editable attributes; every change writes `AuditEvent`; **[L]** audited, not immutable |
| `Proposal`, `Amendment` | payload immutable after creation; only `status` advances, and only with a `ProposalDecision` (proposal) or an approval (amendment) |
| `ReviewItem` | editable only when `review.status ∈ {draft, returned}` |
| Submit | immutable `ReviewVersion(kind=submission)` capturing the full payload + hash + `registry_version` + `output_template_version` |
| Approve | `ReviewVersion(kind=approval, submission_version_id=…)` referencing the exact submission; no payload regeneration from live rows |
| Amend | a separate amendment workspace based on an approved version. Approved `ReviewItem` rows are never edited. Only FNO approval publishes `ReviewVersion(kind=amendment, amends_version_id=…)`; the previous approved version stays official until then |
| Output | rendered from a `ReviewVersion` and its recorded template version, never from live rows |

`edit_revision` counts workspace edits and guards concurrency; `version_no` counts published versions. They are different numbers on purpose.

**[L]** Triggers stop ordinary application writes, not a database owner. True immutability needs append-only storage or an external anchor. Stated, not solved.

---

## 5. Form 4 coverage

**[R]** Map every Form 4 item. **[D]** The registry holds metadata and simple conditions; complex repeating blocks are dedicated components with declared schemas, not a form engine.

| Key | Form 4 section | Primary source facts | Answer |
|---|---|---|---|
| `background` | Background (facility, FBMDR no., identifiers, patient) | `Facility`, `Patient`, `Admission.uin` | `ReviewItem` per field |
| `timing` | 1.a–1.g (admission, death, stay, ICU, intervals) | `Admission`, `Death`, `IcuStay`, `Delivery` | `ReviewItem` per field; intervals derived |
| `admission` | 2. On admission (complaints, G/P/A/L, gestation) | `Observation`, `Admission.complaints` | `ReviewItem` per field |
| `condition` | 3. Condition on admission + referral block | `CareContact`, `AdmissionDiagnosis` | `ReviewItem`; referral block = validated list of 13-attribute rows |
| `diagnosis` | 4. Diagnosis at admission | `AdmissionDiagnosis` | `ReviewItem` |
| `abortion` | 2. Abortion | `Pregnancy.abortion_detail` | `ReviewItem` |
| `antenatal_care` | 3. ANC | `Pregnancy.anc_*` | `ReviewItem` |
| `delivery` | 4. Delivery, puerperium, neonatal | `Delivery`, `Neonate`(n), `Pregnancy.postnatal_*` | `ReviewItem` per field; neonatal block = list |
| `interventions` | 5. Interventions (incl. anaesthesia, complications) | `Intervention`, `Transfusion`(n) | `ReviewItem` matrix + list |
| `primary_diagnosis` | 6. Primary diagnosis | none | `ReviewItem` (judgement) |
| `cause_of_death` | 7. Cause of death | none | `ReviewItem` (judgement) |
| `factors` | 8. Factors present | none | `ReviewItem` per row (judgement) |
| `autopsy` | 9. Autopsy | `Observation` | `ReviewItem` |
| `summary` | 10. Case summary | none | `ReviewItem` |

**[D]** The field inventory (≈150 single-valued fields, plus the declared block schemas) is **generated from the registry**, not hand-written, and reconciled page-by-page against the supplied PDF as the first day-one task. The count is an output, not a claim. It must include: facility name/type/address and nodal contact, FBMDR number/month/year, MCTS and inpatient identifiers, all referral rows and places, every admission diagnosis with underlying cause, every delivery/anaesthesia/complication option, autopsy findings, and the MO/FNO name/designation/date/signature placeholders. No claim of full coverage until that reconciliation passes.

**[D]** Printed labels preserved; internal keys stable. The supplied form repeats section numbers (1–4, then 2–10), so numbers alone are not unique keys. The repetition is the known artefact of the 2017 consolidation of the 2010 form's sections I–III into an unnumbered block — confirmed by comparison with the 2010 Annexure 1, and relevant here only because it forces stable keys. **[D] Key grammar:** `f4.<section_key>.<label>` — `f4.timing.e`, `f4.abortion.a`, `f4.background.facility_name`. The section key, never the printed number, appears in the key: printed 2, 3 and 4 are each split across two registry sections (`admission`/`abortion`, `condition`/`antenatal_care`, `diagnosis`/`delivery`), so a numeric prefix cannot identify a field. `label_printed` keeps the printed numbering for output. Rule keys derive from field keys, so the grammar is fixed before the inventory is generated.

**[D] Field constructs:** single- versus multiple-selection semantics are declared per field, never inferred from checkbox shape. Unknown/N/A exist only where meaningful. "Tick all that apply" → child list; "other, specify" → enum + companion text; signatures → text placeholders, **[L]** not wet or cryptographic signatures.

---

## 6. Reuse engine

```python
Field(key="f4.timing.e", section="timing",
      label_printed="e. Admission – delivery interval",
      type="duration", required=False, required_when=None,
      handling="derive",             # propose | derive | prompt | manual | evidence
      overlap=None,                  # provisional; see Section 6.3
      false_friend_edges=[],         # invalid source→target pairs only
      applicability="delivered",
      rule="f4.timing.e.admission_delivery_interval")
```

**Proposals freeze their inputs.** Each `Proposal.frozen_inputs` entry carries `{kind, ref, label, value, author, entered_by, observed_at, documented_at, entered_at, precision, hash}`. A proposal remains intelligible after the source changes or is superseded.

**Rules** are versioned code returning a value plus inputs, or an explicit refusal:

```python
@rule("f4.timing.e.admission_delivery_interval", version=1, field="f4.timing.e")
def admission_delivery(p):
    d, a = p.delivery, p.reporting_admission
    if d is None:
        return NotComputable("no delivery recorded", state="missing")
    if a is None or a.admitted_at is None:
        return NotComputable("admission time unknown", state="unknown")
    if d.delivered_at is None or d.time_precision != "exact" or a.time_precision != "exact":
        return NotComputable("exact interval unavailable", state="unknown")
    if d.delivered_at < a.admitted_at:
        return NotComputable("delivered before admission to this facility", state="not_applicable")
    return Value(d.delivered_at - a.admitted_at, inputs=[d, a.admitted_at])
```

`NotComputable` separates **missing** (nothing recorded), **unknown** (recorded but not precisely timed) and **not applicable** (the question does not arise). None of them completes a field; a proposed N/A still requires clinician confirmation. Date-only and estimated values stay visible at their precision — no midnight, no invented duration.

**6.3 Overlap categories [R, ?]** — the brief's four categories are in a document not supplied. Two axes are stored: `overlap` (relationship) and `handling` (what the system does). Assignments are **provisional**; if the official definitions differ, assignments may change, not merely their labels.

**[R]** The brief asks for a **reason** per item and an account of terminology and precision differences, not just a category. Every inventory entry therefore carries four fields, and the generated overlap document is one row per field with four columns:

| Field | Content |
|---|---|
| `category` | provisional overlap classification |
| `rationale` | why this field falls in that category, in one sentence, referencing the LCG section or the fact that no source exists |
| `terminology_note` | where the source label and the Form 4 label differ (e.g. "lag alert" vs "prolonged labour"), or `same` |
| `precision_note` | where source precision differs from what Form 4 asks (e.g. charted to the hour vs date-only), or `same` |

An entry with an empty rationale fails the registry test and the build is incomplete.

**6.4 False friends** — the prohibition attaches to the **edge**, not the field. A documented clinician diagnosis may be offered with attribution; an alert crossing may only be evidence *for* that diagnosis. Parity may populate the `Para` field but not Gravida, Abortions or Living children. Each edge carries its own caveat shown beside the source.

Edges barred from `handling=propose`: active-labour diagnosis→admission · "partograph used"→LCG exists · lag alert→prolonged labour · BP/P++→eclampsia · oxytocin/IV fluids→interventions matrix · plan text→case summary · fetal monitoring→neonatal outcome · LCG risk factors→"told antenatally" · no birth recorded→undelivered · last observation→time of death · condition on admission→first observation · LCG duration→hospital stay · onset of labour→active-labour diagnosis · position OP→abnormal presentation.

**6.5 Source-specific rules.** Every threshold belongs to a named, versioned rule set citing its guideline (WHO Labour Care Guide User's Manual; modified WHO partograph), never to "labour data" in general. The LCG and the partograph are different instruments with different action lines and different assessment frequencies, so a rule set may only run on the format it was written for: running a higher-threshold rule set on data collected under a lower one suppresses crossings the original would have raised, and the reverse invents them. The specific cutoffs are read from the cited guideline when the rule set is registered, not asserted here. Any crossing computed after the fact is labelled *computed evidence*, separately from an alert or action a clinician actually documented. With no rule set for a format, observations render **uninterpreted**.

---

## 7. Staleness and conflict

**[D]** Any relevant change — source documents, observations, delivery, death, patient, admission, pregnancy, diagnoses, contacts, interventions, transfusions, neonatal records — triggers `reevaluate(pregnancy)`. For this prototype it runs synchronously inside the application service; no queue, Celery or worker. A shared patient change reevaluates every affected review.

Recompute the proposal set per field and compare against stored proposals:

- **new** — a candidate appeared, including a competing source
- **changed** — recomputed value or inputs differ
- **withdrawn** — no longer computable

For **editable** answers: mark `needs_reconsideration`, retain the old proposals, show the difference. Submission of that field is blocked until the clinician resolves it.

For **submitted or approved** content: never mutate. Write a discrepancy `AuditEvent` recording which answer changed, linked to the version that contained it. The discrepancy belongs to the **review**, not to a particular submission, and stays open until an FNO disposes of it in writing. While any discrepancy is open, approval of that review is blocked — the submission already awaiting approval included. History is never invalidated silently.

Accepted values are never silently replaced, and a rejected candidate never clears an answered field.

Multiple candidates per field are displayed together. No ranking algorithm — deterministic order (same facility, then time precision, then documented time), clinician chooses. **[L]** No automated conflict resolution, by design.

---

## 8. Validation

| Class | Rule | Behaviour |
|---|---|---|
| **Blocking on entry** | internally inconsistent typed value, e.g. `diastolic >= systolic` | refuse the new value; a historical source observation is never edited — it is flagged and requires explicit disposition |
| **Blocking** | `outcome=undelivered` and a `Delivery` exists in this pregnancy | contradiction; cannot submit |
| **Blocking** | required field empty at submit, where requiredness is branch-aware | cannot submit |
| **Blocking** | `needs_reconsideration` on a required or answered field | resolve first |
| **Warning** | death earlier than admission, when not brought-dead and times exact | explain, allow |
| **Informational** | diagnosis recorded with no supporting observations | "supporting observations not recorded", never "inconsistent" |
| **N/A with reason** | delivery before admission to this facility | interval not computable, reason printed |
| **Missing** | `answer_state = unanswered` | listed and linked |

Dropped: obstetric arithmetic (`gravida < para + abortions`), eclampsia-without-BP as a warning, haemorrhage-without-measurement as a warning, delivery-before-admission as a block.

A required question may still be answered "unknown" with a reason; the system does not force unavailable clinical facts to be invented.

---

## 9. Workflow

```
draft ──submit──> submitted ──return──> returned ──submit──> submitted ──approve──> approved
                                                                                      │
                                                              amend ──────────────────┘
```

- Resident authors; FNO returns with a comment or approves.
- **[D]** No self-approval: an FNO may not approve a review they authored, and may not approve an amendment they proposed.
- **[D]** Amendments require FNO approval; only then does a new version become official.
- **[D]** `deadline_at = death + 24h` only when the death time is exact. Otherwise the deadline is shown as uncertain. Late submission is flagged, never blocked.
- **[D]** Voiding is the only removal; drafts are never deleted.

Amendment states are deliberately minimal — `draft → proposed → returned | approved`. One return, then a fresh proposal. A full second review cycle is out of scope.

---

## 10. Output

Printable HTML at Form 4 layout with printed labels, each value marked (`R3` reused, `D1` derived, `E` entered, `C` corrected, `—` none) and a **provenance appendix**: marker, value, origin, source document, observed time, documented time, entered time, original author, entering user, accepted by, decided at, rule and version.

```json
{"form":"FBMDR-2017","review_version":2,"registry_version":"r7","template":"f4-2017@3",
 "generated_at":"...","clinical_time":"...",
 "fields":{"f4.timing.e":{"value":{"hours":15,"minutes":45},"origin":"derived",
   "rule":"f4.timing.e.admission_delivery_interval@1",
   "inputs":[{"ref":"delivery:9","observed_at":"...","precision":"exact","author":"..."}],
   "accepted_by":"..."}}}
```

Rendered from a `ReviewVersion` with its recorded registry and template versions, so historical output is reproducible even after the registry changes. A hash alone does not reconstruct provenance or an old layout, which is why the template version and the payload are both retained.

A **pending amendment** is not a `ReviewVersion`. It renders from `Amendment.payload_json` applied to the template recorded on `Amendment.base_version_id`, and is stamped **DRAFT — NOT APPROVED**. Only an approved amendment publishes a version; until then the base version remains the official output.

---

## 11. UI

1. Case list — four cases, status, returned badge
2. Labour record — timeline, author per entry, late entries marked
3. **Review workspace** — section nav with counts, field list, provenance drawer *(70% of design effort)*
4. Submission check
5. FNO review
6. Form 4 output
7. History

Field row: `[label] [value or state] [source chip] [accept] [reject] [edit]`. HTMX partials, out-of-band counters, mobile-first.

**[D] Autosave:** visible saving / saved / error state, an explicit Save fallback, submit waits for in-flight saves and sends the current `edit_revision`. Out-of-order responses and stale tabs are rejected with a recoverable message and a reload path — never a silent overwrite. Editing a review cannot write to a source table.

**[D] Applicability:** when an upstream answer changes, dependent branches recompute. Inactive branch answers stay in history, are excluded from current output, and require confirmation before being dropped.

---

## 12. Synthetic data

Fixed clinical dates, never `now()`. Audit events and user actions use real server time; any deadline demonstration against historical fixtures runs on a label-led simulated clock.

| Case | Contents | Demonstrates |
|---|---|---|
| **A** | LCG, alert crossing, one missed observation, two authors, one entry documented after death, vaginal delivery, PPH death | core journey; late-entry staleness; three-timestamp provenance |
| **B** | LCG with cervical lag alert → caesarean → sepsis death at 48 h | caesarean after labour; two ICU stays; per-component transfusion |
| **C** | No labour record, died undelivered at 34 weeks (APH) | N/A with reason; unknown applicability |
| **D** | Delivered at PHC 17:40, referral slip, admitted DH 22:10, died 09:40 | negative interval; external source; conflict; indeterminate ordering |

**[D] Fixture rules.** Fictional identities only; no real MCTS numbers, phone numbers or addresses. Clinically coherent timing: observations at the intervals the cited guideline mandates, an assessment recorded after every alert, no observation timestamped before its clinical event, and no chart entry after the time of death unless it is deliberately a late entry and labelled as one. Dates are fixed in the seed; audit and user-action timestamps are real. Seeds are deterministic. Any AI-generated fixture text is reviewed against the LCG and Form 4 before use. No fixture asserts a diagnosis the record does not support — gaps stay gaps.

---

## 13. Security, DPDP, confidentiality

**[D]**

- Server-side object permissions on every view, including source records, histories and exports — not only the review. A resident reaches reviews they authored or are assigned; an FNO reaches all reviews at their facility. Facility scoping is enforced even with one hospital in the demo.
- `Review.assigned_to` exists because assignment-based access is promised; reassignment is not.
- No self-approval for reviews or amendments. Role checks on submit, return, approve, void, amend.
- CSRF on all state-changing requests; no anonymous state-changing GET; secure/HttpOnly/SameSite cookies; login throttling via a maintained dependency listed in the dependency register; no public media URLs; every export authenticated and recorded.
- Local demo settings and production cookie/HTTPS settings are documented separately, so a production-only secure flag cannot make the demo unusable.
- All edits and transitions run in one transaction against the parent review with `edit_revision` checked (`select_for_update` on submit/approve/amend-approve). Stale writes are rejected.
- The application connects as a non-owner database role, so triggers are a real safeguard rather than decoration. Migration/owner credentials are separate.
- Audit payloads are minimal and separately readable; session secrets and full patient payloads never reach ordinary request or error logs.
- **Attribution is preserved internally, including identity.** A separate anonymised sharing output, if built, collapses to role. That export is optional and deferred.
- Confidentiality: blame-flavoured language is banned from UI copy; the review is framed as learning.

**[L]** Not addressed, and stated as gaps: backups/restore, deployment hardening, retention schedule, breach procedure, consent/notice, data-principal rights, storage encryption at rest. Fictional data only. **No claim of DPDP compliance.**

---

## 14. Standards

**[D]** FHIR not adopted. It offers a useful precedent for separating clinical-event time from availability time, and a `Provenance` shape worth copying. The real cost is profiling, identifiers and terminology, which produce nothing reviewable in seven days; future interoperability would need that work anyway, beyond a concept code. We take the two ideas and keep `Observation.value_code` for later mapping. Sources for the two claims: FHIR R4 (v4.0.1), `Observation.issued` — "date/time this version was made available"; and the resource model, which is a serialisation format and does not require a running server.

---

## 15. Testing

Tests are written with each unit, not at the end.

- Model invariants and triggers; approved reviews and published versions reject writes
- Registry: independently reconciled inventory-versus-PDF test — every field resolves to exactly one category and exactly one answer slot, either its own item or a row inside a block item; no entry has an empty rationale
- Reuse: prohibited edges cannot generate proposals; legitimate Para and diagnosis reuse still works
- Derivation: interval and lag rules; every `NotComputable` state, including date-only and estimated time
- Validation: each rule fires on a fixture, stays silent on a clean case, and never edits a historical observation
- Workflow: submit → return → fix → approve → amend, with both submissions preserved and pre-amendment output reproducible
- Staleness: new, changed and withdrawn proposals; conflicting new source after acceptance; patient and admission corrections; accepted value never overwritten
- Concurrency: autosave versus submit/approve; stale tab rejected
- Security: guessed IDs, self-approval, cross-facility access in both directions
- Cross-cutting suite and demo-script rehearsal on day 7

---

## 16. Stack

Django (current LTS) · PostgreSQL · Python 3.12+ · uv · HTMX 2 · Tailwind standalone CLI · pytest / pytest-django / factory_boy · Lucide icons. No SPA, no bundler, no component library, no WhiteNoise unless containerised.

**[D]** Exact versions are pinned in `pyproject.toml`/lockfile and named in the dependency register with exact version, licence, maintenance status, and **the reason this component was chosen** over the alternative considered. "Current LTS" is a selection instruction, not a reproducible declaration.

---

## 17. Build order

Source-to-answer links, state guards, revisions and snapshot shape are built with the first end-to-end case, not retrofitted later.

| Day | Work |
|---|---|
| 1 | Models, migrations, triggers, registry skeleton, **case A end to end** (source → proposal → answer → submit → approve → output), generated inventory reconciled against the PDF |
| 2 | Case list, labour timeline, entry form, auth/roles, object permissions, audited source edits |
| 3 | Rules, proposals, workspace accept/reject/correct, provenance drawer, reconsideration |
| 4 | Remaining sections and blocks (referral, neonatal, transfusion, interventions, ICU); applicability; autosave and resume |
| 5 | Return/approve, lock, amendment workspace, history, reproducible historical output |
| 6 | **Cases B, C, D**; staleness, conflict and discrepancy demo; Form 4 print + JSON for all four cases |
| 7 | Print and JSON regression across all cases; generated overlap document with per-item rationale plus terminology and precision notes; dependency register; security note; cross-cutting tests; demo script |
All four cases must complete the full workflow before any stretch item is touched.

---

## 18. Open questions and defaults [?]

**Ask the assignment author:**

1. The four intended overlap categories in "The core question" — document not supplied.
2. May separate admission, patient and referral records provide reusable values, with LCG-only overlap distinguished?
3. How should Form 4's "partograph used" item represent an LCG? Proposed: retain instrument identity, require an explicit clinician answer, never auto-convert.
4. For ambiguous gestation/time boundaries, may we document our interpretation while preserving the exact source value?

**Our defaults — decided, not blocking:**

- External information is used only if actually supplied; anything unavailable stays unknown.
- Exact death time → displayed 24-hour deadline. Uncertain time → uncertain deadline, no manufactured timestamp.
- Late submission is flagged, not prevented.
- Amendments require FNO approval; no self-approval.
- Unknown death time → indeterminate late-entry status where ordering cannot be established.

---

## 19. Deferred

Two-hospital tenancy · partograph adapter (seam designed, not shipped) · Form 1 generation · pixel-exact paper reproduction and wet-signature fidelity · offline sync (discussed, not built) · candidate ranking · anonymised sharing export · backups and deployment hardening.

---

## 20. What changed from v2

- Answers are explicitly `ReviewItem` only; domain tables are demoted to source facts (Section 2, Section 3, Section 5).
- `Review` gains a reporting facility, an optional reporting admission, `assigned_to`, `edit_revision` and a `voided` state (Section 3).
- `ReviewVersion` records `submission_version_id`, `registry_version` and `output_template_version` (Section 3, Section 10).
- Amendment becomes a payload against a base version with its own approval; approved rows are never edited (Section 3, Section 4, Section 9).
- Supersession extended to `SourceDocument` and `CareContact`, with anti-cycle rules (Section 4).
- `NotComputable` split into missing / unknown / not applicable; precision includes date-only (Section 6).
- False friends attach to edges, not whole fields (Section 6).
- Staleness covers patient/admission changes and adds a discrepancy path for already-submitted content (Section 7).
- BP validation applies to typed values, never to historical observations (Section 8).
- Deadline is conditional on exact death time (Section 9).
- Autosave, applicability recomputation and branch-aware requiredness specified (Section 8, Section 11).
- Multiple ICU stays, per-component transfusion, neonatal time context added (Section 3).
- Security: non-owner DB role, state-changing GET rejection, minimal audit payloads, local-versus-production settings (Section 13).
- Build order restructured so case A is vertical on day 1; cases B–D on day 6; inventory reconciliation independent of the registry (Section 17).

---

## 21. Response to the Codex review

| Codex point | Verdict | Action |
|---|---|---|
| 21.1 Answers, not source rows, are the Form 4 | **Accepted — the most important item.** It removed a real contradiction in Section 5 | Restructured Section 2, Section 3, Section 5 |
| 21.1 Snapshot needs registry/template versions, not just a hash | **Accepted** | Added to `ReviewVersion` and Section 10 |
| 21.1 One representation per repeating block | **Accepted** | `value_json` schema per block; no parallel editable copy |
| 21.2 Obstetric formula as-of admission; no invented precision | **Accepted** | G/P/A/L proposals read the admission-time observation, frozen with as-of context |
| 21.2 `entered_at` server-assigned; authorship not transferred | **Accepted** | Rule stated in Section 3; Section 10 prints author and entering user separately |
| 21.2 Indeterminate, not contemporaneous | **Accepted** | Case D now demonstrates it |
| 21.3 Autosave, stale tabs, branch-aware requiredness | **Accepted** | Section 8, Section 11 |
| 21.4 Inventory must include identifiers, contacts, signatures | **Accepted** | Named explicitly in Section 5 |
| 21.4 ICU list, component transfusion, neonatal time context | **Accepted** | New `IcuStay`, `Transfusion` per component, `Neonate.assessed_at` |
| 21.5 Non-owner DB role, no state-changing GET, minimal audit payloads | **Accepted** | Section 13 |
| 21.7 Guards and snapshots built with case A | **Accepted** | Section 17 rewritten |
| Amendment as a full second state machine | **Partially accepted** | Kept the payload-against-base-version model; reduced to `draft → proposed → returned \| approved`, one return then a fresh proposal |
| Section 5 "historical explanations are unnecessary" | **Disagreed** | The 2010 numbering artefact was verified against the 2010 Annexure 1 and is load-bearing for stable keys; retained with its provenance |
| "Current LTS" as sufficient dependency declaration | **Agreed it is not** | Exact versions pinned and listed in the dependency register |
| Broader review apparatus in Section 21 | **Folded into the body** | A document that says two different things is worse than a shorter one |

The claims match the mechanisms. Where they do not, Section 4 and Section 13 say so.

---

## 22. Consistency pass (3 November 2026)

A cold-read checklist review returned sixteen findings. All sixteen were valid. None changed the architecture; fourteen were contradictions or dangling references introduced when Section 21 was folded into the body, and two were missing assignment deliverables.

| # | Finding | Fix |
|---|---|---|
| 1 | Source facts described as both append-only and editable | Section 2 now separates recorded events from editable attributes, matching Section 4 |
| 2 | Rejecting a proposal both clears and preserves an answer | Section 3 now distinguishes rejection on an unanswered field from rejection of a competing candidate |
| 3 | Block answers specified both per-row and per-block | Section 3: one `ReviewItem` per block, block fields addressed as `field_key#row_index`, each row carrying its own origin |
| 4 | `supersedes_id` required of tables that lack it | Section 4 limits supersession to recorded facts; versions, decisions and audit events never correct |
| 5 | Pending amendment had no renderable version | Section 10: pending amendments render from `Amendment.payload_json` against the base version's template, stamped DRAFT |
| 6 | Section 9 and Section 21 gave different amendment transitions | Section 21 aligned to Section 9 |
| 7 | Discrepancy resolution attached to the wrong submission | Section 7: the discrepancy belongs to the review and blocks any approval until disposed |
| 8 | Referenced `code` column did not exist | Section 14 names `Observation.value_code` |
| 9 | `entered_at` rule claimed but never stated | Section 3 now states it |
| 10 | Frozen inputs omitted the entering user | `entered_by` added to `frozen_inputs` |
| 11 | Threshold direction asserted without a guideline | Section 6.5 binds cutoffs to a cited, versioned rule set and states the consequence rather than the numbers |
| 12 | FHIR claims uncited | Section 14 cites FHIR R4 v4.0.1 with the `Observation.issued` definition |
| 13 | Abbreviations undefined | Section 0 abbreviation list |
| 14 | Overlap deliverable lacked per-item rationale and terminology/precision analysis | Section 6.3 adds `rationale`, `terminology_note`, `precision_note` to every inventory entry |
| 15 | Fixture safety checks unstated | Section 12 fixture rules |
| 16 | Dependency register omitted why each component was chosen | Section 16 |

Two consequences worth naming rather than discovering later. The generated overlap document is now four columns per field, not a bare category list — more work on day 7, and testable. And the pending-amendment render path is a second output path, not a variant of the first, which is why it is scheduled on day 5 rather than day 7.
