# Checks before submission — the rule set

**Status: implemented in `review/checks.py` (rule set `k3`).**

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
- **Not known** is a first-class answer state, separate from N/A. It requires a
  reason and is attributed. It permits submission with a warning for required
  answers such as diagnosis, cause, abortion legality and unavailable autopsy
  results.
- **N/A** is for a question that does not apply. It cannot bypass an
  always-applicable required question or an explicit specification requirement.

## Missing

- [x] **Required registry fields** — primary diagnosis and cause of death 1.a; unanswered blocks, Not known warns, N/A blocks
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

## Reconsideration

- [x] **Changed evidence after acceptance** — an active answered field with `needs_reconsideration` blocks until the clinician accepts, rejects or corrects the new proposal
- [x] **Rejecting the last new candidate** — records the decision and clears reconsideration for that field; other open candidates keep it unresolved
- [x] **Hidden historical answer** — remains a retained warning, not an active blocker
- [x] **Never overwrite** the accepted answer merely because the source changed

## Source records

- [x] **Supersession first** — death/delivery/observation checks use the current head (`superseded_by IS NULL`), not the latest clock time
- [x] **Reporting admission** — use the review's reporting admission, then its linked source admission; no fallback to an unrelated admission
- [x] **Corrected source** — an editable review is flagged until Refresh proposals; that action relinks the source head and marks changed accepted answers for reconsideration
- [x] **Frozen review** — submitted/approved reviews keep their linked source and frozen payload; they are never silently relinked
- [x] **No source fallback** — a review with no linked source does not borrow another document
- [x] **Multiple current heads** — more than one current death or delivery produces a warning; checks use the latest clinical time only as a deterministic fallback

## Precision

- [x] **Exact + exact** — definite ordering
- [x] **Date-only vs date-only** — different dates are definite; the same date is uncertain
- [x] **Estimated or unknown** — cannot establish ordering; a warning explains the uncertainty
- [x] **Future dates** — an exact or date-only future date is invalid; a date-only future date is caught without inventing a time
- [x] **Late entries** — definite late only when the death time and entry time support it; same-day/date-only/estimated is reported as uncertain
- [x] **Discharge** — `discharged_at` is treated as administrative closure unless defined otherwise; discharge after death is a warning, not an impossible clinical event
- [x] **Hospital-stay calculation** — if the administrative discharge is after death, the derived stay ends at death; a discharge before death is used normally

## Impossible

- [x] **Discharge before admission** — warning; `discharged_at` is treated as administrative closure until defined otherwise
- [x] **Discharge after death** — warning; not an impossible clinical event without an explicit definition
- [x] **Admission, death or delivery in the future** — error
- [x] **Negative duration** in the hospital-stay, ICU, admission→delivery or admission→death interval — error
- [x] **Impossible review values** — zero/negative age is an error; age over 120 is a plausibility warning; negative gravida/para/abortions/living children and negative durations (including ICU) are errors
- [x] **Source/review disagreement** — review age differing from the patient record is a warning, distinct from an internally impossible value

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

## Consistency

- [x] **Entered admission–death interval** — compared with entered 1.a/1.b, or exact source times when Form 4 times are absent; one-minute rounding tolerance; warning
- [x] **Entered admission–delivery interval** — compared with exact source times only when delivery is not before admission and the reporting facility matches; warning
- [x] **Entered ICU duration** — compared with exact ICU stay bounds; warning
- [x] **Interval tolerance** — one minute, to absorb rounding; delivery-before-admission and different-facility delivery intervals are skipped
- [x] **Transfusion = no but intervention matrix records transfusion** — warning
- [x] **Pregnancy outcome vs neonatal outcome** — warning for clarification, never automatic correction
- [x] **Multiple births** — mixed outcomes are a warning, not an impossible state
- [x] **No diagnosis-versus-observation rules** — missing evidence is not treated as a wrong diagnosis

## Context warnings

- [x] **Late entries** — labour-record observations definitely documented after death; same-day/date-only/estimated entries are an uncertainty warning
- [x] **No labour record** — only the death/admission records can supply values
- [x] **No labour record linked but observations exist** — no false warning
- [x] **Case summary empty** — nonblocking warning
- [x] **Newer source correction** — warning, or error when an accepted document-sourced answer needs reconsideration

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
- [x] Checks version `k3` is in the frozen payload and submission audit event
- [x] Tests — `tests/test_checks.py`, `tests/test_checks_advanced.py`, `tests/test_legacy.py`
