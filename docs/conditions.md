# Conditional Form 4 — the complete rule set

**Status: implemented in `review/conditions.py` (rule set `c1`).**

A condition hides a printed question; it never answers it. Hidden is not N/A.
A field is hidden only when a recorded answer **definitely** excludes it. If the
controlling answer is missing, the field is shown.

- [x] **Global rule** — unanswered controller → show; definite excluded answer → hide; hidden ≠ N/A
- [x] **Global rule** — a hidden field keeps any previous answer and shows it in the “not shown” list
- [x] **Global rule** — an FNO comment forces its field back into view
- [x] **Global rule** — hidden required fields do not block submission
- [x] **Global rule** — no proposals are created for hidden fields; open proposals are superseded
- [x] **Global rule** — a submitted version freezes `applies` and the reason; approved output is stable

## Whole-section gates

- [x] **2. Abortion** shown only when `1.g Outcome of pregnancy = abortion`
- [x] **4. Delivery, puerperium and neonatal** shown only when outcome is `ectopic`, `live birth`, `still birth` or `undelivered` (hidden for abortion)

## 1. Timing

- [x] **1.e Admission – delivery interval** shown only when outcome is `live birth` or `still birth`

`1.d ICU stay, if any` is optional, not a branch; it stays visible.

## 2. Abortion

- [x] **2.a.i Complete / Incomplete** shown only when `2.a = spontaneous`
- [x] **2.a.ii Legal / Illegal** shown only when `2.a = induced`
- [x] **2.d Centres visited** shown only when `2.d More than one centre = yes`

## 3. Condition on admission + referral

- [x] **3.a.i No. of places visited prior** shown only when `3.a Referred from outside = yes`
- [x] **3.b Referral table** shown only when `3.a Referred from outside = yes`

## 3. Antenatal care

- [x] **3.b Type of facility** shown only when `3.a Did she receive ANC = yes`
- [x] **3.b Other facility, specify** shown only when `3.b Type of facility = other`
- [x] **3.c Services provided by** shown only when `3.a Did she receive ANC = yes`
- [x] **3.c Other specialist, specify** shown only when `3.c Services provided by = other specialist`
- [x] **3.d Told about a disorder / complication** shown only when `3.a = yes`
- [x] **3.e Risk factor identified** shown only when `3.a = yes`

`unknown` is an answer, not a missing one: it is not `yes`, so these follow-ups hide.

## 4. Delivery, puerperium and neonatal

### Outcome-driven

- [x] **4.a Did she have labour pains** shown only when outcome is `live birth`, `still birth` or `undelivered`
- [x] **4.b.i Partograph – past facility** shown only when `4.a Labour pains = yes` **and** `3.a Referred from outside = yes`
- [x] **4.b.ii Partograph – current facility** shown only when `4.a Labour pains = yes`
- [x] **4.c Complications during labour** shown only when outcome is `live birth`, `still birth` or `undelivered`
- [x] **4.f Phase of labour at complication** shown only when outcome is `live birth`, `still birth` or `undelivered`
- [x] **4.g Neonatal outcome** shown only when outcome is `live birth` or `still birth`
- [x] **4.i Postnatal period** shown only when outcome is `live birth` or `still birth`

### Answer-driven

- [x] **4.c Complications – Others, specify** shown only when complications includes `others`
- [x] **4.d Indication (CS / instrumental)** shown only when mode is `caesarean elective`, `caesarean emergency`, `forceps` or `vacuum`
- [x] **4.h Time of neonatal death** shown only when `4.g = neonatal death`
- [x] **4.h Probable cause of neonatal death** shown only when `4.g = neonatal death`
- [x] **4.h Neonatal cause – Others, specify** shown only when the cause includes `others`
- [x] **4.i Probable cause if postnatal eventful** shown only when `4.i = eventful`
- [x] **4.i Postnatal cause – Others, specify** shown only when the cause includes `others`

### No condition beyond section 4

- [x] **4.d Mode of delivery** — visible whenever section 4 is visible
- [x] **4.e Anaesthesia** — visible whenever section 4 is visible
- [x] **4.e Any adverse reaction** — visible whenever section 4 is visible

## 5. Interventions

- [x] **5. No. of units** shown only when `5. Blood transfusion given = yes`
- [x] **5. Components (Cryo / Whole Blood / PRBC / FFP / Platelets)** shown only when `5. Blood transfusion given = yes`
- [x] **5. Transfusion reaction** shown only when `5. Blood transfusion given = yes`

## 9. Autopsy

- [x] **9. Autopsy final diagnosis** shown only when `9. Autopsy performed = yes`

## Deliberately always shown

- [x] Background — all 17 fields
- [x] Timing — 1.a, 1.b, 1.c, 1.d, 1.f, 1.g
- [x] On admission — all 6 fields
- [x] Condition — status and referred
- [x] Diagnosis at admission — the block
- [x] Antenatal care — “Did she receive ANC?”
- [x] Delivery — mode, anaesthesia, adverse reaction
- [x] Interventions — matrix and transfusion given
- [x] Primary diagnosis — the clinician’s conclusion
- [x] Cause of death — all three antecedent lines
- [x] Factors — all 13
- [x] Autopsy — performed
- [x] Summary and sign-off — all 6

## Judgement calls to review

- [x] **Ectopic** keeps section 4 for mode/laparotomy/anaesthesia; labour, partograph, complications, phase, neonatal and postnatal are hidden.
- [x] **ANC “Services provided by”** is gated on received = yes; the print does not put an explicit “if yes” on that line.
- [x] **Partograph – past facility** is gated on referred = yes; inferred from “past facility”, not an explicit printed “if”.
- [x] **Stillbirth and 4.h** stays on the existing registry decision: 4.h only for `neonatal death`, not stillbirth.
- [x] **ICU stay** stays visible; “if any” is optional, not a branch.
- [x] **Referral table** stays whole when referred = yes; rows are not narrowed by “number of places”.
- [x] **Mode options** are not filtered by outcome; contradictions belong to pre-submission checks.
- [x] **Complications when labour pains = no** stays visible; “no pains” is not “no labour”.
- [x] **Phase of labour** stays visible within non-ectopic delivery even when the complications list is empty.
- [x] **Anaesthesia reaction** stays with anaesthesia; the print treats them as one line.

## Where it is enforced

- [x] Workspace rendering and counts — `review/views.py`
- [x] Submission required-field check — `services.missing_required`
- [x] Proposal generation — `services.reevaluate`
- [x] Frozen version payload — `services.canonical_payload`
- [x] Printed output and JSON — `views.output`
- [x] Controller fields reload the page once after save, preserving scroll
- [x] Tests — `tests/test_conditions.py`
