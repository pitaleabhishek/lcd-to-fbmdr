# Checks before submission — the rule set

**Status: implemented in `review/checks.py` (rule set `k2`).**

Checks run when the resident presses **Submit**, not while merely opening or
filling the form. Nothing is shown on first open: a question the resident has not
reached is not an error. When Submit is pressed the checks run once, and the panel
appears only if there is something to say. They only answer three questions:
**is something missing, is a recorded fact impossible, or do two answers
contradict each other?** They never suggest a clinical cause.

- **Error** — blocks submission. The panel opens and no version is created.
- **Warning** — shown in amber. Submission continues only after a single
  **Submit anyway** confirmation; the reviewer decides.
- A check for a missing follow-up only runs when its parent answer is actually
  recorded and says the follow-up applies. A visible-but-unanswered parent does
  not produce a false “missing” error.
- Specification fields are the exception: if the reviewer selects Medical
  conditions or Others, the specification is required even when an upstream
  answer is still unknown.

## Missing

- [x] **Required registry fields** — primary diagnosis and cause of death 1.a
- [x] **Abortion** — spontaneous → complete/incomplete; induced → legal/illegal; more than one centre → centres visited
- [x] **ANC** — received → type of facility, provider and counselling (warnings); counselling → risk factor (warning); facility “other”, provider “other specialist”, Medical conditions and Others must be specified (errors)
- [x] **ANC specification even when the upstream answer is unknown** — if Medical conditions or Others is selected in the risk list, its specification is required
- [x] **Referral** — referred from outside → number of places (warning); the transport/referral/care table is not hidden for self-presenters, but is expected when referred
- [x] **Delivery** — mode missing (warning); caesarean/instrumental → indication (warning); complications include “others” → specify (error)
- [x] **Neonatal** — neonatal outcome missing (warning); baby died (fresh stillbirth, macerated stillbirth or neonatal death) → probable cause (error); cause includes “others” → specify (error)
- [x] **Postnatal** — eventful → probable cause (error); cause includes Medical conditions → specify (error); cause includes “others” → specify (error)
- [x] **Post-birth complication** — phase = post_birth → interval (error)
- [x] **Transfusion** — given → units (error) and components (warning)
- [x] **Autopsy** — performed → final diagnosis (error)
- [x] **Timing** — admission time, death time and outcome of pregnancy missing (warnings; they limit what can be calculated or hidden)
- [x] **Transfusion units = 0** while transfusion is recorded (error)
- [x] **Anaesthesia = “No anaesthesia” plus a specific type** (error)

## Impossible

- [x] **Discharge before admission** — error
- [x] **Discharge after death** — error
- [x] **Admission, death or delivery in the future** — error
- [x] **Negative duration** in the hospital-stay, admission→delivery or admission→death interval — error
- [x] **Impossible age** — zero/negative or over 120 — error

## Possible but unusual — warning, never blocking

- [x] **Death before admission** — a woman can be brought dead
- [x] **Delivery before admission** — a woman can be referred in after delivery; the interval then does not apply
- [x] **Delivery after death** — perimortem delivery is possible
- [x] **Form 4 death time before Form 4 admission time** — brought dead again

## Inconsistent

- [x] **Form 4 outcome vs recorded pregnancy outcome** — warning, because the clinician may be correcting the record
- [x] **Outcome abortion or undelivered, but a delivery is recorded** — error
- [x] **Outcome ectopic, but the delivery mode is not ectopic/laparotomy** — warning
- [x] **Outcome is a birth, but no delivery record exists** — warning
- [x] **Outcome is a birth, but the mode says undelivered** — error
- [x] **Outcome abortion/ectopic/undelivered, but the mode is a birth mode** — warning
- [x] **Retained answer in a question that no longer applies** — warning naming the value and the reason; the answer is kept and not printed
- [x] **Legacy answers from a retired field** — shown in the legacy panel/appendix, never reinterpreted as a current answer
- [x] **Four or more errors at submission** — the toast says how many more there are

## Context warnings

- [x] **Late entries** — labour-record observations documented after the time of death
- [x] **No labour record** — only the death/admission records can supply values
- [x] **No labour record linked but observations exist** — no false warning

## Plain language

- [x] Every message names the printed item, not the internal key
- [x] Impossible dates include both actual times
- [x] Every message says what to do next
- [x] Each issue links to the field, unless the field is hidden; hidden answers are named in the message instead
- [x] The panel appears only after Submit is pressed
- [x] Errors open the panel; warnings require one confirmation
- [x] The resident note survives a blocked submit
- [x] Inline messages appear at the field as well as in the panel, only after Submit

## What is deliberately not checked

- [x] No suggested cause of death, diagnosis or contributing factor
- [x] No clinical probability or “likely” language
- [x] No forcing of optional fields
- [x] No check of internal keys the user cannot see

## Where it is enforced

- [x] Workspace panel and inline messages, shown after Submit — `review/views.py`, `workspace.html`
- [x] Submission — `services.submit` refuses while any error remains
- [x] Required-field helper — `services.missing_required` delegates to `checks.required_keys`
- [x] Tests — `tests/test_checks.py`
