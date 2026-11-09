# Form 4 and LCG overlap

This file maps all 99 Form 4 fields to Dr Atter's four categories.

| Category | Fields | Reused | Derived | Entered |
|---|---:|---:|---:|---:|
| 1. Patient info and admin records | 22 | 7 | 0 | 15 |
| 2. Clinical and OBS information | 48 | 5 | 4 | 39 |
| 3. Mx and interventions | 9 | 1 | 0 | 8 |
| 4. Death investigation and review | 20 | 0 | 0 | 20 |
| **Total** | **99** | **13** | **4** | **82** |

**Finding: the app can reuse 1 of 99 fields (1.0%) directly from the LCG. That
field is 2.b Para.**

The other 12 reused values come from patient, facility, admission, death,
delivery, pregnancy or neonate records. The app derives four values from exact
times. The clinician enters the remaining 82 values. No LCG value exists for
them.

`Reused` means the app copies a recorded fact without change. `Derived` means the
app calculates the value from facts. `Entered` means the clinician supplies the
answer and owns it.

## Terminology and precision

- **Parity and para:** the LCG records parity as births after viability. Form 4
  para is the nearest match. The LCG has no abortions or living children beside
  it.
- **Partograph:** Form 4 asks if the staff used a partograph. The LCG is not a
  partograph. Do not fill this field from the LCG.
- **Labour pains:** the LCG charts labour onset and contractions. It does not chart
  pain.
- **Referral table:** the form has one printed row for each place. The app stores
  one row for each place. Times use minutes. Money uses rupees.
- **Diagnosis table:** the form has seven printed diagnosis groups and one row for
  each group. Detail and underlying cause are free text.
- **Intervention matrix:** the matrix has five phases and twelve procedures. It
  records if a procedure was present. It does not record a dose.
- **MCTS:** the LCG does not record it.
- **Sign-off:** the block has one date. It does not have a separate date for each
  signature.
- **Timing:** the app stores Form 4 intervals in minutes. It offers a derived
  interval only when exact times exist and both events belong to the same
  admission and facility. If a woman was referred in after delivery, 1.e is N/A.
- **False friends:** partograph, labour pains, complications, interventions and
  neonatal outcome look reusable. They are not. They are clinician data or data
  from another record.

## Appendix: all 99 fields

### 1. Patient info and admin records (22)

Identity and facility data come from patient, facility and review records, not the LCG.

| Form 4 item | Source | Relationship | Basis / note |
|---|---|---|---|
| Name of health facility | Facility / review | Reused | Reporting facility |
| Type of health facility | Clinician | Entered |  |
| Address | Clinician | Entered |  |
| Name of Nodal Person | Clinician | Entered |  |
| Nodal contact No. | Clinician | Entered |  |
| FBMDR No. (specific to the place) | Facility / review | Reused | Review number |
| MCTS No. | Patient record | Reused | Patient record. The LCG does not record MCTS. |
| Month | Clinician | Entered |  |
| Year | Clinician | Entered |  |
| Full name of deceased mother | Patient record | Reused | Patient record |
| Age | Patient record | Reused | Patient record |
| Inpatient No. | Admission | Reused | Admission number |
| Medico-legal admission | Admission | Reused | Admission flag |
| Complete address | Clinician | Entered |  |
| Contact / mobile No. | Clinician | Entered |  |
| Education | Clinician | Entered |  |
| Below Poverty Line | Clinician | Entered |  |
| Form filled by the MO on duty - name | Clinician | Entered |  |
| Nodal Officer - name | Clinician | Entered |  |
| Designation | Clinician | Entered |  |
| Address of the Institution | Clinician | Entered |  |
| Stamp & Date | Clinician | Entered | one date for the sign-off block |

### 2. Clinical and OBS information (48)

The LCG supplies only parity. Timing comes from admission, death and delivery records. The rest is other structured facts or clinical judgement.

| Form 4 item | Source | Relationship | Basis / note |
|---|---|---|---|
| 1.a Date and time of admission | Admission | Reused | Admission time |
| 1.b Date and time of death | Death record | Reused | Death time |
| 1.c Duration of hospital stay | Admission | Derived | Admission → exit |
| 1.d Duration of ICU stay, if any | Admission | Derived | Sum of ICU stays |
| 1.e Admission - delivery interval | Delivery record | Derived | Admission → delivery |
| 1.f Admission - death interval | Death record | Derived | Admission → death |
| 1.g Outcome of pregnancy | Pregnancy record | Reused | Pregnancy outcome |
| 2.a Complaints at time of admission | Clinician | Entered |  |
| 2.b Gravida | Clinician | Entered |  |
| 2.b Para | LCG | Reused | LCG header parity. The LCG records parity as births after viability. It has no abortions or living children. |
| 2.b Abortions | Clinician | Entered |  |
| 2.b No. of living children | Clinician | Entered |  |
| 2.c Period of gestation | Clinician | Entered |  |
| 3. Condition on admission | Clinician | Entered |  |
| 3.a Referred from outside | Clinician | Entered |  |
| 3.a.i No. of places visited prior | Clinician | Entered |  |
| 3.b Referral table (13 attributes per place) | Clinician | Entered | one printed row per place. The model stores one row per place. Times use minutes. Money uses rupees (Rs.). |
| 4. Diagnosis table (diagnosis + underlying cause) | Clinician | Entered | seven printed diagnosis groups, one row each. Underlying cause is free text, as printed. |
| 2.a Spontaneous / Induced | Clinician | Entered |  |
| 2.a.i Complete / Incomplete | Clinician | Entered |  |
| 2.a.ii Legal / Illegal | Clinician | Entered |  |
| 2.b Procedure adopted | Clinician | Entered |  |
| 2.c Post-abortal period | Clinician | Entered |  |
| 2.d Procedure in more than one centre | Clinician | Entered |  |
| 2.d Centres visited | Clinician | Entered |  |
| 3.a Did she receive ANC | Clinician | Entered |  |
| 3.b Type of facility | Clinician | Entered |  |
| 3.b Other facility, specify | Clinician | Entered |  |
| 3.c Services provided by | Clinician | Entered |  |
| 3.c Other specialist, specify | Clinician | Entered |  |
| 3.d Told about a disorder / complication | Clinician | Entered |  |
| 3.e Risk factor identified | Clinician | Entered |  |
| 3.e Medical conditions, specify | Clinician | Entered |  |
| 3.e Others, specify | Clinician | Entered |  |
| 4.a Did she have labour pains | Clinician | Entered | the LCG charts labour onset and contractions, not pain |
| 4.b.i Partograph used - past facility | Clinician | Entered |  |
| 4.b.ii Partograph used - current facility | Clinician | Entered | the form asks about a partograph. The LCG is not one. The app keeps the instrument identity and never auto-converts. |
| 4.c Complications during labour | Clinician | Entered |  |
| 4.c Others, specify | Clinician | Entered |  |
| 4.f Phase of labour at complication | Clinician | Entered |  |
| 4.f Post-birth complication interval | Clinician | Entered |  |
| 4.g Neonatal outcome | Neonate record | Reused | Neonate record |
| 4.h Probable cause of death if baby died | Clinician | Entered |  |
| 4.h Others, specify | Clinician | Entered |  |
| 4.i Postnatal period | Clinician | Entered |  |
| 4.i Probable cause if eventful | Clinician | Entered |  |
| 4.i Medical conditions, specify | Clinician | Entered |  |
| 4.i Others, specify | Clinician | Entered |  |

### 3. Mx and interventions (9)

The delivery record supplies the mode. Anaesthesia, transfusion and the procedure matrix are not recorded in a form the LCG can supply.

| Form 4 item | Source | Relationship | Basis / note |
|---|---|---|---|
| 4.d Mode of delivery | Delivery record | Reused | Delivery record |
| 4.d Indication (CS / instrumental) | Clinician | Entered |  |
| 4.e Anaesthesia | Clinician | Entered |  |
| 4.e Any adverse reaction | Clinician | Entered |  |
| 5. Interventions matrix (phase x procedure) | Clinician | Entered | five phases by twelve procedures. The matrix records presence per cell, not dose. |
| 5. Blood transfusion given | Clinician | Entered |  |
| 5. No. of units | Clinician | Entered |  |
| 5. If yes, No of units (Cryo / Whole Blood / PRBC / FFP / Platelets) | Clinician | Entered |  |
| 5. Transfusion reaction | Clinician | Entered |  |

### 4. Death investigation and review (20)

These are the reviewer's conclusions and the review's own record. None is a labour observation.

| Form 4 item | Source | Relationship | Basis / note |
|---|---|---|---|
| 6. Primary diagnosis / condition leading to death | Clinician | Entered |  |
| 7. Part 1 a. Due to or as a consequence of | Clinician | Entered |  |
| 7. Part 1 b. Due to or as a consequence of | Clinician | Entered |  |
| 7. Part 1 c. Due to or as a consequence of | Clinician | Entered |  |
| 8. Delay in woman seeking help | Clinician | Entered |  |
| 8. Refusal of treatment or admission | Clinician | Entered |  |
| 8. Refusal of admission in previous facility | Clinician | Entered |  |
| 8. Lack of transport from home to health care facility | Clinician | Entered |  |
| 8. Lack of transport between health care facilities | Clinician | Entered |  |
| 8. Lack of assured referral system | Clinician | Entered |  |
| 8. Lack of facilities, equipment or consumable | Clinician | Entered |  |
| 8. Lack of blood / blood products | Clinician | Entered |  |
| 8. Lack of OT availability | Clinician | Entered |  |
| 8. Lack of human resources | Clinician | Entered |  |
| 8. Lack of Anaesthetist | Clinician | Entered |  |
| 8. Lack of Obstetricians | Clinician | Entered |  |
| 8. Lack of expertise, training or education | Clinician | Entered |  |
| 9. Autopsy performed | Clinician | Entered |  |
| 9. Autopsy final diagnosis | Clinician | Entered |  |
| 10. Case summary | Clinician | Entered |  |
