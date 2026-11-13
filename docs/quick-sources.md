# Form 4 sources: the 99 fields and where they come from

This is the field-by-field contract behind the quick clinical review.
If a document supplies a value, `/review/<pk>/quick/` does not ask for it:
the value is accepted automatically and the provenance names the document.
Only fields with no document (clinical judgement) appear as questions.

- Form 4 fields: **99** (every one is classified)
- Supplied by a record document: **76** (8 documents)
- Wired to a rule today: **44**
- Assigned but not wired yet: **32**
- Clinical judgement: **23** (10 questions plus 13 contributing-factor checkboxes)

## Coverage

The eight documents cover 76 of 99 fields (77%). The other 23 are clinical
judgement. Coverage means every field has an assigned source; it does not mean
every assigned field is auto-filled yet. Values are never invented to close the
gap: a field with no capture stays blank and is listed below.

| Key | Document | Fields | Auto now | Not wired |
|---|---|---|---|---|
| `patient_record` | Patient record | 7 | 7 | 0 |
| `anc_card` | ANC card | 13 | 9 | 4 |
| `admission_register` | Admission register | 9 | 8 | 1 |
| `labour_record` | Labour record (LCG) | 7 | 1 | 6 |
| `ot_note` | OT / delivery note | 18 | 8 | 10 |
| `referral_slip` | Referral slip | 4 | 0 | 4 |
| `death_record` | Death record / postmortem | 3 | 1 | 2 |
| `fbmdr_register` | FBMDR register | 15 | 10 | 5 |

### Not wired yet

**ANC card**
- `f4.antenatal_care.facility_other` — 3.b Other facility, specify (only applies when the parent option is chosen)
- `f4.antenatal_care.provider_other` — 3.c Other specialist, specify (only applies when the parent option is chosen)
- `f4.antenatal_care.risks_medical` — 3.e Medical conditions, specify (only applies when the parent option is chosen)
- `f4.antenatal_care.risks_others` — 3.e Others, specify (only applies when the parent option is chosen)

**Admission register**
- `f4.diagnosis.rows` — 4. Diagnosis table (diagnosis + underlying cause) (structured table; no source model yet)

**Labour record (LCG)**
- `f4.delivery.labour_pains` — 4.a Did she have labour pains (no source capture yet)
- `f4.delivery.partograph_current` — 4.b.ii Partograph used - current facility (no source capture yet)
- `f4.delivery.complications` — 4.c Complications during labour (no source capture yet)
- `f4.delivery.complications_other` — 4.c Others, specify (only applies when the parent option is chosen)
- `f4.delivery.phase` — 4.f Phase of labour at complication (no source capture yet)
- `f4.delivery.post_birth_complication_time` — 4.f Post-birth complication interval (no source capture yet)

**OT / delivery note**
- `f4.abortion.multiple_centres` — 2.d Procedure in more than one centre (no source capture yet)
- `f4.abortion.centres` — 2.d Centres visited (only applies when the parent option is chosen)
- `f4.delivery.mode_indication` — 4.d Indication (CS / instrumental) (no source capture yet)
- `f4.delivery.anaesthesia` — 4.e Anaesthesia (no source capture yet)
- `f4.delivery.anaesthesia_reaction` — 4.e Any adverse reaction (no source capture yet)
- `f4.interventions.matrix` — 5. Interventions matrix (phase x procedure) (structured table; no source model yet)
- `f4.interventions.transfusion_given` — 5. Blood transfusion given (no source capture yet)
- `f4.interventions.transfusion_units` — 5. No. of units (no source capture yet)
- `f4.interventions.transfusion_components` — 5. If yes, No of units (Cryo / Whole Blood / PRBC / FFP / Platelets) (no source capture yet)
- `f4.interventions.transfusion_reaction` — 5. Transfusion reaction (no source capture yet)

**Referral slip**
- `f4.condition.referred` — 3.a Referred from outside (no source capture yet)
- `f4.condition.places` — 3.a.i No. of places visited prior (no source capture yet)
- `f4.condition.referral` — 3.b Referral table (13 attributes per place) (structured table; no source model yet)
- `f4.delivery.partograph_past` — 4.b.i Partograph used - past facility (no source capture yet)

**Death record / postmortem**
- `f4.autopsy.performed` — 9. Autopsy performed (no source capture yet)
- `f4.autopsy.diagnosis` — 9. Autopsy final diagnosis (no source capture yet)

**FBMDR register**
- `f4.summary.mo_name` — Form filled by the MO on duty - name (no source capture yet)
- `f4.summary.fno_name` — Nodal Officer - name (no source capture yet)
- `f4.summary.designation` — Designation (no source capture yet)
- `f4.summary.institution_address` — Address of the Institution (no source capture yet)
- `f4.summary.signed_on` — Stamp & Date (no source capture yet)

## The eight documents

| Key | Document | Fields | Wired |
|---|---|---|---|
| `patient_record` | Patient record | 7 | 7 |
| `anc_card` | ANC card | 13 | 9 |
| `admission_register` | Admission register | 9 | 8 |
| `labour_record` | Labour record (LCG) | 7 | 1 |
| `ot_note` | OT / delivery note | 18 | 8 |
| `referral_slip` | Referral slip | 4 | 0 |
| `death_record` | Death record / postmortem | 3 | 1 |
| `fbmdr_register` | FBMDR register | 15 | 10 |

## Field matrix

`Auto today` means a rule fills the field from the record now. A blank means
the document is assigned but the value is not wired yet; it stays blank rather
than being invented.

| # | Section | Form 4 item | Type | Document | Auto today | Rule | Clinician page |
|---|---|---|---|---|---|---|---|
| 1 | Background | Name of health facility | text | FBMDR register | yes | `f4.background.facility_name.from_facility` | no |
| 2 | Background | Type of health facility | text | FBMDR register | yes | `f4.background.facility_type.from_facility` | no |
| 3 | Background | Address | text | FBMDR register | yes | `f4.background.facility_address.from_facility` | no |
| 4 | Background | Name of Nodal Person | text | FBMDR register | yes | `f4.background.nodal_name.from_facility` | no |
| 5 | Background | Nodal contact No. | text | FBMDR register | yes | `f4.background.nodal_contact.from_facility` | no |
| 6 | Background | FBMDR No. (specific to the place) | text | FBMDR register | yes | `f4.background.fbmdr_no.from_review` | no |
| 7 | Background | MCTS No. | text | Patient record | yes | `f4.background.mcts_no.from_patient` | no |
| 8 | Background | Month | int | FBMDR register | yes | `f4.background.fbmdr_month.from_review` | no |
| 9 | Background | Year | int | FBMDR register | yes | `f4.background.fbmdr_year.from_review` | no |
| 10 | Background | Full name of deceased mother | text | Patient record | yes | `f4.background.name.from_patient` | no |
| 11 | Background | Age | int | Patient record | yes | `f4.background.age.from_patient` | no |
| 12 | Background | Inpatient No. | text | FBMDR register | yes | `f4.background.inpatient_no.from_admission` | no |
| 13 | Background | Medico-legal admission | enum | FBMDR register | yes | `f4.background.medico_legal.from_admission` | no |
| 14 | Background | Complete address | text | Patient record | yes | `f4.background.address.from_patient` | no |
| 15 | Background | Contact / mobile No. | text | Patient record | yes | `f4.background.contact.from_patient` | no |
| 16 | Background | Education | enum | Patient record | yes | `f4.background.education.from_patient` | no |
| 17 | Background | Below Poverty Line | enum | Patient record | yes | `f4.background.bpl.from_patient` | no |
| 18 | 1. Timing a-g | 1.a Date and time of admission | datetime | Admission register | yes | `f4.timing.a.from_admission` | no |
| 19 | 1. Timing a-g | 1.b Date and time of death | datetime | Death record / postmortem | yes | `f4.timing.b.from_death` | no |
| 20 | 1. Timing a-g | 1.c Duration of hospital stay | duration | Admission register | yes | `f4.timing.c.admission_to_exit` | no |
| 21 | 1. Timing a-g | 1.d Duration of ICU stay, if any | duration | Admission register | yes | `f4.timing.d.icu_total` | no |
| 22 | 1. Timing a-g | 1.e Admission - delivery interval | duration | Admission register | yes | `f4.timing.e.admission_to_delivery` | no |
| 23 | 1. Timing a-g | 1.f Admission - death interval | duration | Admission register | yes | `f4.timing.f.admission_to_death` | no |
| 24 | 1. Timing a-g | 1.g Outcome of pregnancy | enum | OT / delivery note | yes | `f4.timing.g.from_pregnancy` | no |
| 25 | 2. On admission | 2.a Complaints at time of admission | text | Admission register | yes | `f4.admission.complaints.from_admission` | no |
| 26 | 2. On admission | 2.b Gravida | int | ANC card | yes | `f4.admission.gravida.from_pregnancy` | no |
| 27 | 2. On admission | 2.b Para | int | Labour record (LCG) | yes | `f4.admission.para.from_lcg` | no |
| 28 | 2. On admission | 2.b Abortions | int | ANC card | yes | `f4.admission.abortions.from_pregnancy` | no |
| 29 | 2. On admission | 2.b No. of living children | int | ANC card | yes | `f4.admission.living_children.from_pregnancy` | no |
| 30 | 2. On admission | 2.c Period of gestation | enum | ANC card | yes | `f4.admission.gestation.from_pregnancy` | no |
| 31 | 3. Condition on admission + referral | 3. Condition on admission | enum | Admission register | yes | `f4.condition.status.from_admission` | no |
| 32 | 3. Condition on admission + referral | 3.a Referred from outside | enum | Referral slip |  |  | no |
| 33 | 3. Condition on admission + referral | 3.a.i No. of places visited prior | int | Referral slip |  |  | no |
| 34 | 3. Condition on admission + referral | 3.b Referral table (13 attributes per place) | block | Referral slip |  |  | no |
| 35 | 4. Diagnosis at admission | 4. Diagnosis table (diagnosis + underlying cause) | block | Admission register |  |  | no |
| 36 | 2. Abortion | 2.a Spontaneous / Induced | enum | OT / delivery note | yes | `f4.abortion.type.from_pregnancy` | no |
| 37 | 2. Abortion | 2.a.i Complete / Incomplete | enum | OT / delivery note | yes | `f4.abortion.spontaneous_type.from_pregnancy` | no |
| 38 | 2. Abortion | 2.a.ii Legal / Illegal | enum | OT / delivery note | yes | `f4.abortion.induced_legality.from_pregnancy` | no |
| 39 | 2. Abortion | 2.b Procedure adopted | enum | OT / delivery note | yes | `f4.abortion.procedure.from_pregnancy` | no |
| 40 | 2. Abortion | 2.c Post-abortal period | enum | OT / delivery note | yes | `f4.abortion.post_abortal.from_pregnancy` | no |
| 41 | 2. Abortion | 2.d Procedure in more than one centre | enum | OT / delivery note |  |  | no |
| 42 | 2. Abortion | 2.d Centres visited | text | OT / delivery note |  |  | no |
| 43 | 3. Antenatal care | 3.a Did she receive ANC | enum | ANC card | yes | `f4.antenatal_care.received.from_pregnancy` | no |
| 44 | 3. Antenatal care | 3.b Type of facility | enum | ANC card | yes | `f4.antenatal_care.facility.from_pregnancy` | no |
| 45 | 3. Antenatal care | 3.b Other facility, specify | text | ANC card |  |  | no |
| 46 | 3. Antenatal care | 3.c Services provided by | enum | ANC card | yes | `f4.antenatal_care.provider.from_pregnancy` | no |
| 47 | 3. Antenatal care | 3.c Other specialist, specify | text | ANC card |  |  | no |
| 48 | 3. Antenatal care | 3.d Told about a disorder / complication | enum | ANC card | yes | `f4.antenatal_care.counselled.from_pregnancy` | no |
| 49 | 3. Antenatal care | 3.e Risk factor identified | multi | ANC card | yes | `f4.antenatal_care.risks.from_pregnancy` | no |
| 50 | 3. Antenatal care | 3.e Medical conditions, specify | text | ANC card |  |  | no |
| 51 | 3. Antenatal care | 3.e Others, specify | text | ANC card |  |  | no |
| 52 | 4. Delivery, puerperium and neonatal | 4.a Did she have labour pains | enum | Labour record (LCG) |  |  | no |
| 53 | 4. Delivery, puerperium and neonatal | 4.b.i Partograph used - past facility | enum | Referral slip |  |  | no |
| 54 | 4. Delivery, puerperium and neonatal | 4.b.ii Partograph used - current facility | enum | Labour record (LCG) |  |  | no |
| 55 | 4. Delivery, puerperium and neonatal | 4.c Complications during labour | multi | Labour record (LCG) |  |  | no |
| 56 | 4. Delivery, puerperium and neonatal | 4.c Others, specify | text | Labour record (LCG) |  |  | no |
| 57 | 4. Delivery, puerperium and neonatal | 4.d Mode of delivery | enum | OT / delivery note | yes | `f4.delivery.mode.from_delivery` | no |
| 58 | 4. Delivery, puerperium and neonatal | 4.d Indication (CS / instrumental) | text | OT / delivery note |  |  | no |
| 59 | 4. Delivery, puerperium and neonatal | 4.e Anaesthesia | multi | OT / delivery note |  |  | no |
| 60 | 4. Delivery, puerperium and neonatal | 4.e Any adverse reaction | text | OT / delivery note |  |  | no |
| 61 | 4. Delivery, puerperium and neonatal | 4.f Phase of labour at complication | enum | Labour record (LCG) |  |  | no |
| 62 | 4. Delivery, puerperium and neonatal | 4.f Post-birth complication interval | enum | Labour record (LCG) |  |  | no |
| 63 | 4. Delivery, puerperium and neonatal | 4.g Neonatal outcome | enum | OT / delivery note | yes | `f4.delivery.neonatal.from_neonate` | no |
| 64 | 4. Delivery, puerperium and neonatal | 4.h Probable cause of death if baby died | multi | **Clinical judgement** |  |  | yes |
| 65 | 4. Delivery, puerperium and neonatal | 4.h Others, specify | text | **Clinical judgement** |  |  | yes |
| 66 | 4. Delivery, puerperium and neonatal | 4.i Postnatal period | enum | Admission register | yes | `f4.delivery.postnatal.from_pregnancy` | no |
| 67 | 4. Delivery, puerperium and neonatal | 4.i Probable cause if eventful | multi | **Clinical judgement** |  |  | yes |
| 68 | 4. Delivery, puerperium and neonatal | 4.i Medical conditions, specify | text | **Clinical judgement** |  |  | yes |
| 69 | 4. Delivery, puerperium and neonatal | 4.i Others, specify | text | **Clinical judgement** |  |  | yes |
| 70 | 5. Interventions | 5. Interventions matrix (phase x procedure) | block | OT / delivery note |  |  | no |
| 71 | 5. Interventions | 5. Blood transfusion given | enum | OT / delivery note |  |  | no |
| 72 | 5. Interventions | 5. No. of units | int | OT / delivery note |  |  | no |
| 73 | 5. Interventions | 5. If yes, No of units (Cryo / Whole Blood / PRBC / FFP / Platelets) | multi | OT / delivery note |  |  | no |
| 74 | 5. Interventions | 5. Transfusion reaction | enum | OT / delivery note |  |  | no |
| 75 | 6. Primary diagnosis | 6. Primary diagnosis / condition leading to death | text | **Clinical judgement** |  |  | yes |
| 76 | 7. Cause of death | 7. Part 1 a. Due to or as a consequence of | text | **Clinical judgement** |  |  | yes |
| 77 | 7. Cause of death | 7. Part 1 b. Due to or as a consequence of | text | **Clinical judgement** |  |  | yes |
| 78 | 7. Cause of death | 7. Part 1 c. Due to or as a consequence of | text | **Clinical judgement** |  |  | yes |
| 79 | 8. Factors present | 8. Delay in woman seeking help | enum | **Clinical judgement** |  |  | yes |
| 80 | 8. Factors present | 8. Refusal of treatment or admission | enum | **Clinical judgement** |  |  | yes |
| 81 | 8. Factors present | 8. Refusal of admission in previous facility | enum | **Clinical judgement** |  |  | yes |
| 82 | 8. Factors present | 8. Lack of transport from home to health care facility | enum | **Clinical judgement** |  |  | yes |
| 83 | 8. Factors present | 8. Lack of transport between health care facilities | enum | **Clinical judgement** |  |  | yes |
| 84 | 8. Factors present | 8. Lack of assured referral system | enum | **Clinical judgement** |  |  | yes |
| 85 | 8. Factors present | 8. Lack of facilities, equipment or consumable | enum | **Clinical judgement** |  |  | yes |
| 86 | 8. Factors present | 8. Lack of blood / blood products | enum | **Clinical judgement** |  |  | yes |
| 87 | 8. Factors present | 8. Lack of OT availability | enum | **Clinical judgement** |  |  | yes |
| 88 | 8. Factors present | 8. Lack of human resources | enum | **Clinical judgement** |  |  | yes |
| 89 | 8. Factors present | 8. Lack of Anaesthetist | enum | **Clinical judgement** |  |  | yes |
| 90 | 8. Factors present | 8. Lack of Obstetricians | enum | **Clinical judgement** |  |  | yes |
| 91 | 8. Factors present | 8. Lack of expertise, training or education | enum | **Clinical judgement** |  |  | yes |
| 92 | 9. Autopsy | 9. Autopsy performed | enum | Death record / postmortem |  |  | no |
| 93 | 9. Autopsy | 9. Autopsy final diagnosis | text | Death record / postmortem |  |  | no |
| 94 | 10. Case summary and sign-off | 10. Case summary | text | **Clinical judgement** |  |  | yes |
| 95 | 10. Case summary and sign-off | Form filled by the MO on duty - name | text | FBMDR register |  |  | no |
| 96 | 10. Case summary and sign-off | Nodal Officer - name | text | FBMDR register |  |  | no |
| 97 | 10. Case summary and sign-off | Designation | text | FBMDR register |  |  | no |
| 98 | 10. Case summary and sign-off | Address of the Institution | text | FBMDR register |  |  | no |
| 99 | 10. Case summary and sign-off | Stamp & Date | date | FBMDR register |  |  | no |

## The clinician page asks only this

| Form 4 item | Why no document can answer it |
|---|---|
| 4.h Probable cause of death if baby died | Probable cause for the baby: a judgement, and conditional. |
| 4.h Others, specify | Free-text detail of the neonatal cause judgement. |
| 4.i Probable cause if eventful | Probable cause in the postnatal period: a judgement. |
| 4.i Medical conditions, specify | Free-text detail of the postnatal cause judgement. |
| 4.i Others, specify | Free-text detail of the postnatal cause judgement. |
| 6. Primary diagnosis / condition leading to death | A synthesised diagnosis, not a record field. |
| 7. Part 1 a. Due to or as a consequence of | Part 1 of the death certificate chain: a judgement. |
| 7. Part 1 b. Due to or as a consequence of | Part 1 chain, next antecedent. |
| 7. Part 1 c. Due to or as a consequence of | Part 1 chain, underlying antecedent. |
| 10. Case summary | The case summary is written, not read from a form. |
| 8. Factors present (13 checkboxes) | Whether a health-system factor contributed is the reviewer's assessment. |

## GPLA

| Item | Document | Source |
|---|---|---|
| G | ANC card | `Pregnancy.gravida` |
| P | Labour record (LCG) | `SourceDocument.header_json.parity` |
| L | ANC card | `Pregnancy.living_children` |
| A | ANC card | `Pregnancy.abortions` |

The LCG header carries parity only. Gravida, living children and abortions are
ANC-card history and are stored on the pregnancy, not on the labour chart.

## How automatic acceptance works

1. On draft/returned review load, `services.reevaluate` computes proposals from facts.
2. `services.auto_accept_record_values` accepts every proposal whose field has a document.
3. A value the author typed or corrected is never overwritten. The clinician's
   answer wins and the record candidate is closed; the collapsed section marks
   the value **overridden**.
4. Provenance records the document label and the decision reason `Auto-filled from <document>`.
5. Clinical-judgement proposals, if any, are left for the reviewer; there are none today.

## Deliberate limits

- A document-sourced field with no rule yet stays blank rather than being invented.
  The list above is the work queue for deeper record capture.
- The LCG labour record supplies parity only. Mode, the baby's outcome and the
  pregnancy outcome come from the delivery note.
- The app does not invent clinical conclusions to make the form look complete.
- Hidden conditional fields keep their answers but are not shown or printed.
