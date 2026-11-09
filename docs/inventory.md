# Form 4 overlap inventory

This file lists all 99 fields from the registry. The categories follow Dr Atter (4 November 2026). The app derives each relationship from the rules.

**Direct LCG reuse: 1 of 99 fields (1.0%).** The clinician enters each other value, or the app copies it from another recorded fact.

## By category

| Category | Fields |
|---|---|
| 1. Patient info and admin records | 22 |
| 2. Clinical and OBS information | 48 |
| 3. Mx and interventions | 9 |
| 4. Death ix and review | 20 |

## By source of the value

| Source | Fields |
|---|---|
| clinician | 82 |
| admin | 4 |
| patient_record | 3 |
| admission | 3 |
| death | 2 |
| delivery | 2 |
| pregnancy | 1 |
| lcg | 1 |
| neonate | 1 |

## By relationship

| Relationship | Fields |
|---|---|
| reused | 13 |
| derived | 4 |
| none | 82 |

## Fields

| Key | Category | Source | Printed item | Relationship | PDF label found |
|---|---|---|---|---|---|
| `f4.background.facility_name` | 1 | admin | Name of health facility | reused | yes |
| `f4.background.facility_type` | 1 | clinician | Type of health facility | none | yes |
| `f4.background.facility_address` | 1 | clinician | Address | none | yes |
| `f4.background.nodal_name` | 1 | clinician | Name of Nodal Person | none | yes |
| `f4.background.nodal_contact` | 1 | clinician | Nodal contact No. | none | yes |
| `f4.background.fbmdr_no` | 1 | admin | FBMDR No. (specific to the place) | reused | yes |
| `f4.background.mcts_no` | 1 | patient_record | MCTS No. | reused | yes |
| `f4.background.fbmdr_month` | 1 | clinician | Month | none | yes |
| `f4.background.fbmdr_year` | 1 | clinician | Year | none | yes |
| `f4.background.name` | 1 | patient_record | Full name of deceased mother | reused | yes |
| `f4.background.age` | 1 | patient_record | Age | reused | yes |
| `f4.background.inpatient_no` | 1 | admin | Inpatient No. | reused | yes |
| `f4.background.medico_legal` | 1 | admin | Medico-legal admission | reused | yes |
| `f4.background.address` | 1 | clinician | Complete address | none | yes |
| `f4.background.contact` | 1 | clinician | Contact / mobile No. | none | yes |
| `f4.background.education` | 1 | clinician | Education | none | yes |
| `f4.background.bpl` | 1 | clinician | Below Poverty Line | none | yes |
| `f4.timing.a` | 2 | admission | 1.a Date and time of admission | reused | yes |
| `f4.timing.b` | 2 | death | 1.b Date and time of death | reused | yes |
| `f4.timing.c` | 2 | admission | 1.c Duration of hospital stay | derived | yes |
| `f4.timing.d` | 2 | admission | 1.d Duration of ICU stay, if any | derived | yes |
| `f4.timing.e` | 2 | delivery | 1.e Admission - delivery interval | derived | yes |
| `f4.timing.f` | 2 | death | 1.f Admission - death interval | derived | yes |
| `f4.timing.g` | 2 | pregnancy | 1.g Outcome of pregnancy | reused | yes |
| `f4.admission.complaints` | 2 | clinician | 2.a Complaints at time of admission | none | yes |
| `f4.admission.gravida` | 2 | clinician | 2.b Gravida | none | yes |
| `f4.admission.para` | 2 | lcg | 2.b Para | reused | yes |
| `f4.admission.abortions` | 2 | clinician | 2.b Abortions | none | yes |
| `f4.admission.living_children` | 2 | clinician | 2.b No. of living children | none | yes |
| `f4.admission.gestation` | 2 | clinician | 2.c Period of gestation | none | yes |
| `f4.condition.status` | 2 | clinician | 3. Condition on admission | none | yes |
| `f4.condition.referred` | 2 | clinician | 3.a Referred from outside | none | yes |
| `f4.condition.places` | 2 | clinician | 3.a.i No. of places visited prior | none | yes |
| `f4.condition.referral` | 2 | clinician | 3.b Referral table (13 attributes per place) | none | yes |
| `f4.diagnosis.rows` | 2 | clinician | 4. Diagnosis table (diagnosis + underlying cause) | none | yes |
| `f4.abortion.type` | 2 | clinician | 2.a Spontaneous / Induced | none | yes |
| `f4.abortion.spontaneous_type` | 2 | clinician | 2.a.i Complete / Incomplete | none | yes |
| `f4.abortion.induced_legality` | 2 | clinician | 2.a.ii Legal / Illegal | none | yes |
| `f4.abortion.procedure` | 2 | clinician | 2.b Procedure adopted | none | yes |
| `f4.abortion.post_abortal` | 2 | clinician | 2.c Post-abortal period | none | yes |
| `f4.abortion.multiple_centres` | 2 | clinician | 2.d Procedure in more than one centre | none | yes |
| `f4.abortion.centres` | 2 | clinician | 2.d Centres visited | none | yes |
| `f4.antenatal_care.received` | 2 | clinician | 3.a Did she receive ANC | none | yes |
| `f4.antenatal_care.facility` | 2 | clinician | 3.b Type of facility | none | yes |
| `f4.antenatal_care.facility_other` | 2 | clinician | 3.b Other facility, specify | none | yes |
| `f4.antenatal_care.provider` | 2 | clinician | 3.c Services provided by | none | yes |
| `f4.antenatal_care.provider_other` | 2 | clinician | 3.c Other specialist, specify | none | yes |
| `f4.antenatal_care.counselled` | 2 | clinician | 3.d Told about a disorder / complication | none | yes |
| `f4.antenatal_care.risks` | 2 | clinician | 3.e Risk factor identified | none | yes |
| `f4.antenatal_care.risks_medical` | 2 | clinician | 3.e Medical conditions, specify | none | yes |
| `f4.antenatal_care.risks_others` | 2 | clinician | 3.e Others, specify | none | yes |
| `f4.delivery.labour_pains` | 2 | clinician | 4.a Did she have labour pains | none | yes |
| `f4.delivery.partograph_past` | 2 | clinician | 4.b.i Partograph used - past facility | none | yes |
| `f4.delivery.partograph_current` | 2 | clinician | 4.b.ii Partograph used - current facility | none | yes |
| `f4.delivery.complications` | 2 | clinician | 4.c Complications during labour | none | yes |
| `f4.delivery.complications_other` | 2 | clinician | 4.c Others, specify | none | yes |
| `f4.delivery.mode` | 3 | delivery | 4.d Mode of delivery | reused | yes |
| `f4.delivery.mode_indication` | 3 | clinician | 4.d Indication (CS / instrumental) | none | yes |
| `f4.delivery.anaesthesia` | 3 | clinician | 4.e Anaesthesia | none | yes |
| `f4.delivery.anaesthesia_reaction` | 3 | clinician | 4.e Any adverse reaction | none | yes |
| `f4.delivery.phase` | 2 | clinician | 4.f Phase of labour at complication | none | yes |
| `f4.delivery.post_birth_complication_time` | 2 | clinician | 4.f Post-birth complication interval | none | yes |
| `f4.delivery.neonatal_outcome` | 2 | neonate | 4.g Neonatal outcome | reused | yes |
| `f4.delivery.neonatal_cause` | 2 | clinician | 4.h Probable cause of death if baby died | none | yes |
| `f4.delivery.neonatal_cause_other` | 2 | clinician | 4.h Others, specify | none | yes |
| `f4.delivery.postnatal` | 2 | clinician | 4.i Postnatal period | none | yes |
| `f4.delivery.postnatal_cause` | 2 | clinician | 4.i Probable cause if eventful | none | yes |
| `f4.delivery.postnatal_cause_medical` | 2 | clinician | 4.i Medical conditions, specify | none | yes |
| `f4.delivery.postnatal_cause_other` | 2 | clinician | 4.i Others, specify | none | yes |
| `f4.interventions.matrix` | 3 | clinician | 5. Interventions matrix (phase x procedure) | none | yes |
| `f4.interventions.transfusion_given` | 3 | clinician | 5. Blood transfusion given | none | yes |
| `f4.interventions.transfusion_units` | 3 | clinician | 5. No. of units | none | yes |
| `f4.interventions.transfusion_components` | 3 | clinician | 5. If yes, No of units (Cryo / Whole Blood / PRBC / FFP / Platelets) | none | yes |
| `f4.interventions.transfusion_reaction` | 3 | clinician | 5. Transfusion reaction | none | yes |
| `f4.primary_diagnosis.dx` | 4 | clinician | 6. Primary diagnosis / condition leading to death | none | yes |
| `f4.cause_of_death.a_antecedent` | 4 | clinician | 7. Part 1 a. Due to or as a consequence of | none | yes |
| `f4.cause_of_death.b_antecedent` | 4 | clinician | 7. Part 1 b. Due to or as a consequence of | none | yes |
| `f4.cause_of_death.c_antecedent` | 4 | clinician | 7. Part 1 c. Due to or as a consequence of | none | yes |
| `f4.factors.delay_seeking_help` | 4 | clinician | 8. Delay in woman seeking help | none | yes |
| `f4.factors.refusal_treatment` | 4 | clinician | 8. Refusal of treatment or admission | none | yes |
| `f4.factors.refusal_previous_facility` | 4 | clinician | 8. Refusal of admission in previous facility | none | yes |
| `f4.factors.transport_from_home` | 4 | clinician | 8. Lack of transport from home to health care facility | none | yes |
| `f4.factors.transport_between_facilities` | 4 | clinician | 8. Lack of transport between health care facilities | none | yes |
| `f4.factors.referral_system` | 4 | clinician | 8. Lack of assured referral system | none | yes |
| `f4.factors.facilities_equipment` | 4 | clinician | 8. Lack of facilities, equipment or consumable | none | yes |
| `f4.factors.facilities_blood` | 4 | clinician | 8. Lack of blood / blood products | none | yes |
| `f4.factors.facilities_ot` | 4 | clinician | 8. Lack of OT availability | none | yes |
| `f4.factors.human_resources` | 4 | clinician | 8. Lack of human resources | none | yes |
| `f4.factors.anaesthetist` | 4 | clinician | 8. Lack of Anaesthetist | none | yes |
| `f4.factors.obstetricians` | 4 | clinician | 8. Lack of Obstetricians | none | yes |
| `f4.factors.expertise` | 4 | clinician | 8. Lack of expertise, training or education | none | yes |
| `f4.autopsy.performed` | 4 | clinician | 9. Autopsy performed | none | yes |
| `f4.autopsy.diagnosis` | 4 | clinician | 9. Autopsy final diagnosis | none | yes |
| `f4.summary.text` | 4 | clinician | 10. Case summary | none | yes |
| `f4.summary.mo_name` | 1 | clinician | Form filled by the MO on duty - name | none | yes |
| `f4.summary.fno_name` | 1 | clinician | Nodal Officer - name | none | yes |
| `f4.summary.designation` | 1 | clinician | Designation | none | yes |
| `f4.summary.institution_address` | 1 | clinician | Address of the Institution | none | yes |
| `f4.summary.signed_on` | 1 | clinician | Stamp & Date | none | yes |
