# Checks before submission

A check is a deterministic test that runs before submit. It does not diagnose. It answers three questions:

1. Is something missing?
2. Is a recorded fact impossible?
3. Do two answers contradict each other?

The code is in `review/checks.py`. This file explains what the checks do. It is not
the UI guide and not the clinical rulebook.

## Run and severity

Checks run only on **Check before submitting** or **Submit**. They do not run when
the form opens.

| Result | Effect |
|---|---|
| Error | Blocks submit. The app creates no version. |
| Warning | Shows in amber. The user must select **Submit anyway** once. |

`Check` creates no version. `Submit` creates one only if the app finds no errors.

## Groups

| Group | What it catches |
|---|---|
| Missing | Required answers, follow-ups and specification fields |
| Impossible | Future dates, negative values, zero units, exclusive answers |
| Inconsistent | Two answers disagree, or an answer and the source disagree |
| Uncertain | Time precision cannot establish order |
| Possible or needs review | Unusual but clinically possible |
| Source record | A newer source correction needs review |

## Panel

The panel appears after Check or a failed Submit. It is grouped and plain.

- The bar stays below the legend and stays visible when the form scrolls.
- The full list is closed by default.
- Up and down arrows move between issues.
- **Where** opens the question, the empty block table or the hidden-question row.
- A hidden retained answer can be cleared there.
- A check about the whole record returns to the checks bar.

## Missing

| Rule | Effect |
|---|---|
| Required registry fields | Error for primary diagnosis, cause of death 1.a and answered blocks. N/A on a required field is an error. |
| Abortion | Spontaneous needs complete or incomplete. Induced needs legal or illegal. More than one centre needs the centres. |
| ANC | Received needs facility, provider and counselling (warnings). Counselling needs a risk factor (warning). Facility “other”, provider “other specialist”, Medical conditions and Others need a specification (errors). |
| ANC with an unknown parent | Medical conditions and Others still need a specification when selected. |
| Referral | Referred from outside needs the number of places (warning). The transport, referral and care table is expected when referred. It stays available to self-presenters. |
| Delivery | Missing mode is a warning. Caesarean or instrumental needs an indication (warning). Complications with Others need a specification (error). |
| Neonatal | Missing outcome is a warning. A baby who died needs a probable cause (error). Cause with Others needs a specification (error). |
| Postnatal | Eventful needs a probable cause (error). Medical conditions and Others need a specification (error). |
| Post-birth complication | Phase `post_birth` needs the interval (error). |
| Transfusion | Given needs units (error) and components (warning). |
| Autopsy | Performed needs the final diagnosis (error). |
| Timing | Missing admission time, death time or pregnancy outcome gives warnings. |
| Transfusion units | Zero while transfusion is recorded is an error. |
| Anaesthesia | “No anaesthesia” plus a specific type is an error. |

A follow-up is checked only when the parent answer is recorded and shows that the
follow-up applies. A visible but unanswered parent does not cause a false
“missing” error. Specification fields are the exception. N/A cannot bypass an
always-required field or a selected specification.

## Reconsideration

| Rule | Effect |
|---|---|
| Changed evidence after acceptance | An active answered field with `needs_reconsideration` blocks submit until the clinician decides. |
| Reject the last new candidate | The app clears reconsideration for that field. Other candidates keep it open. |
| Hidden historical answer | Stays as a retained warning. It does not block. |
| Source change | The app never overwrites an accepted answer. |

## Source records

| Rule | Effect |
|---|---|
| Current correction | Death, delivery and observation checks use the current row (`superseded_by IS NULL`), not the latest clock time. |
| Reporting admission | Use the review admission, then its linked source admission. Do not use an unrelated admission. |
| Corrected source | An editable review stays flagged until Refresh proposals. That action links the current source and marks changed accepted answers. |
| Frozen review | Submitted and approved reviews keep their source and payload. The app never relinks them. |
| No source fallback | A review without a source does not borrow another document. |
| Multiple current records | More than one current death or delivery gives a warning. Checks use the latest clinical time as a fallback. |

## Dates and precision

| Rule | Effect |
|---|---|
| Exact plus exact | The app can establish order. |
| Date-only plus date-only | Different dates establish order. The same date is uncertain. |
| Estimated or unknown | The app cannot establish order. A warning explains this. |
| Future dates | An exact or date-only future date is invalid. |
| Late entries | Definite late only when the death time and entry time show it. Same-day, date-only or estimated entries are uncertain. |
| Discharge | `discharged_at` is administrative closure. Discharge after death is a warning. |
| Hospital stay | If discharge is after death, the stay ends at death. A discharge before death is used normally. |

## Impossible values

| Rule | Effect |
|---|---|
| Discharge before admission | Warning. |
| Discharge after death | Warning, not an impossible clinical event. |
| Future admission, death or delivery | Error. |
| Negative duration | Error for hospital stay, ICU, admission to delivery and admission to death. |
| Review values | Zero or negative age is an error. Age over 120 is a plausibility warning. Negative gravida, para, abortions, living children and durations are errors. |
| Source and review age | A difference is a warning. It is separate from an impossible value. |

## Possible but unusual

These are warnings. They never block.

- Death before admission, including brought dead.
- Delivery before admission. The interval then does not apply.
- Delivery after death. Perimortem delivery is possible.
- Form 4 death time before Form 4 admission time.

## Inconsistent

| Rule | Effect |
|---|---|
| Form 4 outcome and pregnancy outcome differ | Warning. The clinician may be correcting the record. |
| Abortion or undelivered, but a delivery exists | Error. |
| Ectopic, but mode is not ectopic or laparotomy | Warning. |
| Birth, but no delivery record | Warning. |
| Birth, but mode says undelivered | Error. |
| Abortion, ectopic or undelivered, but mode is a birth mode | Warning. |
| Retained answer in a hidden question | Warning with the value and reason. The app keeps it and does not print it. |
| Legacy answer from a retired field | Shown in the legacy panel or appendix. Never treated as current. |
| Four or more errors | The toast says how many more errors exist. |

## Consistency

| Rule | Effect |
|---|---|
| Entered admission-death interval | Compare with 1.a and 1.b, or exact source times. One-minute tolerance. Warning. |
| Entered admission-delivery interval | Compare with exact source times only if delivery is not before admission and the facility matches. Warning. |
| Entered ICU duration | Compare with exact ICU bounds. Warning. |
| Interval tolerance | One minute. Skip delivery before admission and delivery at another facility. |
| Transfusion is no but the matrix records it | Warning. |
| Pregnancy outcome and neonatal outcome differ | Warning. The app does not correct either. |
| Multiple births with mixed outcomes | Warning, not an impossible state. |
| Diagnosis and observation | Missing evidence is not a wrong diagnosis. |

## Context warnings

| Rule | Effect |
|---|---|
| Late entries | Definite late when staff documented a labour entry after death. Same-day, date-only or estimated entries are uncertain. |
| No labour record | Only the death and admission records can supply values. |
| Observations but no labour record | No false warning. |
| Empty case summary | Nonblocking warning. |
| Newer source correction | Warning. Error if an accepted source answer needs reconsideration. |

## Plain language

- Each message names the printed item, not the internal key.
- Impossible-date messages include both times.
- Each message says what to do next.
- Each issue links to the field. If hidden, the message names the answer.
- The panel appears only after Check or Submit.
- The bar stays visible. The full list is closed.
- The submit area shows a short summary and **View all checks**.
- Errors open the panel. Warnings need one confirmation.
- The resident note survives a blocked submit.
- Inline messages appear after Submit only.

## Enforcement

- Panel and inline messages: `review/views.py` and `workspace.html`.
- Submit refusal: `services.submit`.
- Required fields: `services.missing_required` and `checks.required_keys`.
- Frozen version: the checks version is in the payload and the submission audit event.
- Amendments run the same checks on submit and approval.
- Tests: `test_checks.py`, `test_checks_advanced.py`, `test_legacy.py`,
  `test_amendments.py`.
