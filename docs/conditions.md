# Conditional Form 4 — the rule set

**Status: implemented in `review/conditions.py` (rule set `c2`).**

A condition hides a printed question; it never answers it. Hidden is not N/A.
A field is hidden only when a recorded answer **definitely** excludes it.

- [x] **Global rule** — unanswered controller → show; definite excluded answer → hide; hidden ≠ N/A
- [x] **Global rule** — a hidden field keeps any previous answer and shows it in the “not shown” list or legacy panel
- [x] **Global rule** — an FNO comment forces its field back into view
- [x] **Global rule** — hidden required fields do not block submission
- [x] **Global rule** — no proposals are created for hidden fields; open proposals are superseded
- [x] **Global rule** — a submitted version freezes `applies` and the reason; approved output is stable

## Printed requirements vs implementation interpretations

The first group is what the PDF itself says. The second group is our reading of an
ambiguous printed layout; these are not verified government branching rules.

**Printed requirements**

- [x] **4.f Post Birth timing** — the bands under “Post Birth” describe when the
  **mother** developed a complication after birth. They are not the baby’s time
  of death. Shown when `4.f Phase = post_birth`, independently of the baby.
- [x] **3.e follows 3.d** — risk factor follows “If yes, was she told about a
  disorder/complication?”. Risks therefore require ANC received **and**
  counselling answered yes.
- [x] **3.a.i places** — printed under “If referred from outside”.
- [x] **3.e / 4.i “Specify” cells** — Medical conditions and Others each have a
  separate specification cell.
- [x] **4.h** — printed as “If baby died, probable cause of death”.

**Implementation interpretations**

- [x] **4.h and stillbirth** — we show the probable-cause list for
  `fresh_still_birth`, `macerated_still_birth` **and** `neonatal_death`, because
  the print says “If baby died” and `4.g` includes both stillbirth options. The
  PDF does not explicitly say whether stillbirth should use this table. We do
  not infer a cause from the stillbirth type.
- [x] **3.b transport/referral/care table** — kept available even when
  `3.a referred = no`, because the printed table includes Home/Village,
  transport and time to reach, which can apply to a self-presenting woman. Only
  `3.a.i places` remains referral-only.
- [x] **4.e anaesthesia** — kept available for abortion even though section 4 is
  headed “If applicable”, because the abortion section has no anaesthesia or
  adverse-reaction question and the intervention matrix records anaesthesia but
  not an adverse reaction. Only anaesthesia and its reaction are exposed for
  abortion; labour, mode, neonatal and postnatal fields remain hidden.
- [x] **“No anaesthesia”** — a new explicit option in `4.e Anaesthesia`. The
  printed form has only three anaesthesia types; without this option, an empty
  answer would mean “unknown”, not “none”. The follow-up reaction is hidden only
  when this explicit option is the sole answer.

## Whole-section gates

- [x] **2. Abortion** shown only when `1.g Outcome of pregnancy = abortion`
- [x] **4. Delivery, puerperium and neonatal** shown only when outcome is
  `ectopic`, `live birth`, `still birth` or `undelivered`
- [x] **4.e Anaesthesia and 4.e adverse reaction** are exempt from the section
  gate, so they remain available for abortion. No other delivery field is exempt.

## 1. Timing

- [x] **1.e Admission – delivery interval** shown only when outcome is `live birth`
  or `still birth`

`1.d ICU stay, if any` stays visible; “if any” is optional, not a branch.

## 2. Abortion

- [x] **2.a.i Complete / Incomplete** shown only when `2.a = spontaneous`
- [x] **2.a.ii Legal / Illegal** shown only when `2.a = induced`
- [x] **2.d Centres visited** shown only when `2.d More than one centre = yes`

## 3. Condition on admission + referral

- [x] **3.a.i No. of places visited prior** shown only when
  `3.a Referred from outside = yes`
- [x] **3.b Transport/referral/care table** always available; it is not hidden by
  `referred = no`

## 3. Antenatal care

`WhenYes` is used only for these ANC gates: unanswered → UNKNOWN, yes → TRUE,
no → FALSE, unknown → UNKNOWN. Unknown is uncertainty, not a definite negative;
the follow-up remains available but is not treated as definitely required.

- [x] **3.b Type of facility** shown when `3.a Did she receive ANC` is yes or unknown
- [x] **3.b Other facility, specify** shown when `3.b = other`
- [x] **3.c Services provided by** shown when `3.a` is yes or unknown
- [x] **3.c Other specialist, specify** shown when `3.c = other specialist`
- [x] **3.d Told about a disorder / complication** shown when `3.a` is yes or unknown
- [x] **3.e Risk factor identified** shown when **both** `3.a` and `3.d` are yes
  (or either is unknown, but not when either is no)
- [x] **3.e Medical conditions, specify** shown when the risk list includes
  `medical_conditions`
- [x] **3.e Others, specify** shown when the risk list includes `others`

A retained `counselled = yes` cannot keep risks alive when `received = no`.
Risks carry both ANC checks in their own rule, not only through the parent chain.

## 4. Delivery, puerperium and neonatal

### Outcome-driven

- [x] **4.a Did she have labour pains** shown when outcome is live birth, still
  birth or undelivered
- [x] **4.b.i Partograph – past facility** shown when `4.a = yes` and
  `3.a Referred from outside = yes`
- [x] **4.b.ii Partograph – current facility** shown when `4.a = yes`
- [x] **4.c Complications during labour** shown when outcome is live birth, still
  birth or undelivered
- [x] **4.f Phase of labour at complication** shown when outcome is live birth,
  still birth or undelivered
- [x] **4.g Neonatal outcome** shown when outcome is live birth or still birth
- [x] **4.i Postnatal period** shown when outcome is live birth or still birth

### Answer-driven

- [x] **4.c Complications – Others, specify** shown when complications includes
  `others`
- [x] **4.d Indication (CS / instrumental)** shown when mode is caesarean
  elective, caesarean emergency, forceps or vacuum
- [x] **4.f Post-birth complication interval** shown only when
  `4.f Phase = post_birth`, independent of the baby’s outcome. Options match the
  print: “Within ≤ 6 hrs. of birth”, “> 6 - ≤ 24 hrs. of birth”,
  “> 24 hrs. after birth”.
- [x] **4.h Probable cause of death if baby died** shown when neonatal outcome is
  `fresh_still_birth`, `macerated_still_birth` or `neonatal_death`; hidden when
  alive; visible when the outcome is unanswered (conservative).
- [x] **4.h Others, specify** shown when the cause list includes `others`
- [x] **4.i Probable cause if postnatal eventful** shown when `4.i = eventful`
- [x] **4.i Medical conditions, specify** shown when the postnatal cause includes
  `medical_conditions`
- [x] **4.i Others, specify** shown when the postnatal cause includes `others`
- [x] **4.e Any adverse reaction** hidden only when Anaesthesia is explicitly
  `No anaesthesia`; shown when anaesthesia was given or is unanswered/unknown
- [x] **4.e Anaesthesia and adverse reaction** remain available for abortion;
  all other section 4 fields remain hidden

## 5. Interventions

- [x] **5. No. of units** shown only when `5. Blood transfusion given = yes`
- [x] **5. Components** shown only when transfusion given = yes
- [x] **5. Transfusion reaction** shown only when transfusion given = yes

## 9. Autopsy

- [x] **9. Autopsy final diagnosis** shown only when `9. Autopsy performed = yes`

## Deliberately always shown

- [x] Background — all 17 fields
- [x] Timing — 1.a, 1.b, 1.c, 1.d, 1.f, 1.g
- [x] On admission — all 6 fields
- [x] Condition — status, referred and the transport/referral/care table
- [x] Diagnosis at admission — the block
- [x] Antenatal care — “Did she receive ANC?”
- [x] Interventions — matrix and transfusion given
- [x] Primary diagnosis — the clinician’s conclusion
- [x] Cause of death — all three antecedent lines
- [x] Factors — all 13
- [x] Autopsy — performed
- [x] Summary and sign-off — all 6

## Legacy answers

- [x] **Retired field** — `f4.delivery.neonatal_death_time` is not part of the
  active form. Its old answers are kept under `LEGACY_FIELDS`, shown as
  “Previous form answers” and never mapped onto the post-birth interval.
- [x] **Old frozen versions** — active fields absent from a frozen payload are
  not shown; retired payload fields remain in the “Previous form fields” appendix.
- [x] **No reinterpretation** — a previous neonatal-death timing answer is not
  copied to `f4.delivery.post_birth_complication_time`.

## Where it is enforced

- [x] Workspace rendering and counts — `review/views.py`
- [x] Submission required-field check — `services.missing_required`
- [x] Proposal generation — `services.reevaluate`
- [x] Frozen version payload — `services.canonical_payload`
- [x] Printed output and JSON — `views.output`
- [x] Controller fields reload the page once after save, preserving scroll
- [x] Tests — `tests/test_conditions.py`, `tests/test_legacy.py`
