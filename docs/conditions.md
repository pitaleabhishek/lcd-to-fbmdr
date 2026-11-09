# Conditional Form 4: rule set

The rule set is version 2 in `review/conditions.py`.

A condition hides a printed question. It never answers the question. A hidden
question is not N/A. The app hides a field only when a recorded answer definitely
excludes it.

## General rules

- An unanswered controller shows the field.
- A definite excluded answer hides the field.
- A hidden field keeps its old answer. The app shows the answer in “not shown” or
  in the legacy panel.
- If a parent is N/A, its child is hidden.
- An FNO comment forces the field back into view.
- A hidden required field does not block submission.
- The app creates no proposal for a hidden field. It replaces open proposals.
- A submitted version freezes `applies` and the reason.

## Printed form and implementation choices

The printed form says:

- **4.f Post-birth timing**: the bands show when the mother developed a
  complication after birth. They do not show the baby's time of death. The field
  shows when `4.f Phase = post_birth`. It does not depend on the baby.
- **3.e follows 3.d**: risk factors need ANC received and counselling answered
  yes.
- **3.a.i places**: the printed form places this question under “If referred from
  outside”.
- **3.e and 4.i “Specify” cells**: Medical conditions and Others each have their
  own specification cell.
- **4.h**: the printed text is “If baby died, probable cause of death”.

The implementation makes these choices:

- **4.h and stillbirth**: the probable-cause list shows for fresh stillbirth,
  macerated stillbirth and neonatal death. The app does not infer a cause from the
  stillbirth type.
- **3.b transport, referral and care table**: the table stays available when
  referred = no. Home or village, transport and time to reach can apply to a
  self-presenter. Only 3.a.i places depends on referral.
- **4.e anaesthesia**: the field is available for abortion. The abortion section
  has no anaesthesia or adverse-reaction question. The app shows only anaesthesia
  and its reaction for abortion. Labour, mode, neonatal and postnatal fields stay
  hidden.
- **“No anaesthesia”**: this is an explicit option. An empty answer means unknown,
  not none. The app hides the reaction only when this option is the only answer.

## Section gates

- **2. Abortion** shows only when outcome = abortion.
- **4. Delivery, puerperium and neonatal** shows only when outcome is ectopic,
  live birth, still birth or undelivered.
- **4.e Anaesthesia and adverse reaction** do not obey the section gate. No other
  delivery field is exempt.

## 1. Timing

- **1.e Admission to delivery interval** shows only when outcome is live birth or
  still birth.
- **1.d ICU stay** always shows. “If any” means optional. It is not a branch.

## 2. Abortion

- **2.a.i Complete or Incomplete** shows only when 2.a = spontaneous.
- **2.a.ii Legal or Illegal** shows only when 2.a = induced.
- **2.d Centres visited** shows only when more than one centre = yes.

## 3. Condition and referral

- **3.a.i Number of places visited** shows only when referred from outside = yes.
- **3.b Transport, referral and care table** always shows. Referred = no does not
  hide it.

## 3. Antenatal care

`WhenYes` works as follows:

- unanswered: unknown.
- yes: true.
- no: false.
- unknown: unknown.

Unknown means uncertainty. It is not a definite no.

- **3.b Type of facility** shows when ANC received is yes or unknown.
- **3.b Other facility, specify** shows when facility = other.
- **3.c Services provided by** shows when ANC received is yes or unknown.
- **3.c Other specialist, specify** shows when provider = other specialist.
- **3.d Told about a disorder or complication** shows when ANC received is yes or
  unknown.
- **3.e Risk factor identified** shows when received and counselled are both yes,
  or either is unknown. It does not show when either is no.
- **3.e Medical conditions, specify** shows when risks include medical conditions.
- **3.e Others, specify** shows when risks include others.

A retained `counselled = yes` does not keep risks visible when `received = no`.

## 4. Delivery, puerperium and neonatal

Outcome-driven fields:

- **4.a Labour pains** shows for live birth, still birth or undelivered.
- **4.b.i Partograph, past facility** shows when labour pains = yes and referred =
  yes.
- **4.b.ii Partograph, current facility** shows when labour pains = yes.
- **4.c Complications during labour** shows for live birth, still birth or
  undelivered.
- **4.f Phase of labour at complication** shows for live birth, still birth or
  undelivered.
- **4.g Neonatal outcome** shows for live birth or still birth.
- **4.i Postnatal period** shows for live birth or still birth.

Answer-driven fields:

- **4.c Complications, Others** shows when complications include others.
- **4.d Indication (CS or instrumental)** shows when mode is caesarean elective,
  caesarean emergency, forceps or vacuum.
- **4.f Post-birth complication interval** shows when phase = post_birth. It does
  not depend on the baby. The options are within 6 hours, over 6 to 24 hours, and
  over 24 hours.
- **4.h Probable cause of death if baby died** shows for fresh stillbirth,
  macerated stillbirth or neonatal death. It hides when the baby is alive. It
  shows when the outcome is unanswered.
- **4.h Others** shows when the cause includes others.
- **4.i Probable cause if postnatal eventful** shows when postnatal = eventful.
- **4.i Medical conditions** shows when the postnatal cause includes medical
  conditions.
- **4.i Others** shows when the postnatal cause includes others.
- **4.e Any adverse reaction** hides only when anaesthesia is explicitly none. It
  shows when anaesthesia was given, unanswered or unknown.
- **4.e Anaesthesia and adverse reaction** stay available for abortion. All other
  section 4 fields stay hidden.

## 5. Interventions

- **5. Number of units** shows when transfusion given = yes.
- **5. Components** shows when transfusion given = yes.
- **5. Transfusion reaction** shows when transfusion given = yes.

## 9. Autopsy

- **9. Autopsy final diagnosis** shows when autopsy performed = yes.

## Always shown

- Background: all 17 fields.
- Timing: 1.a, 1.b, 1.c, 1.d, 1.f and 1.g.
- On admission: all 6 fields.
- Condition: status, referred and the transport, referral and care table.
- Diagnosis at admission: the block.
- Antenatal care: “Did she receive ANC?”.
- Interventions: the matrix and transfusion given.
- Primary diagnosis: the clinician conclusion.
- Cause of death: all three antecedent lines.
- Factors: all 13.
- Autopsy: performed.
- Summary and sign-off: all 6.

## Legacy answers

- **Retired field**: `f4.delivery.neonatal_death_time` is not active. Old answers
  stay in `LEGACY_FIELDS` and show as “Previous form answers”.
- **Old frozen versions**: active fields that are absent from a frozen payload do
  not show. Retired payload fields stay in the “Previous form fields” appendix.
- **No reinterpretation**: the app does not copy an old neonatal-death timing
  answer to `f4.delivery.post_birth_complication_time`.

## Enforcement

- Workspace rendering and counts: `review/views.py`.
- Required-field check: `services.missing_required`.
- Proposal generation: `services.reevaluate`.
- Frozen payload: `services.canonical_payload`.
- Printed output and JSON: `views.output`.
- A controller field reloads the page once after save. It keeps the scroll
  position.
- An amendment evaluates conditions on staged answers. The approved review keeps
  its frozen `applies` flags.
- Tests: `tests/test_conditions.py`, `tests/test_legacy.py` and
  `tests/test_amendments.py`.
