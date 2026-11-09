# Form 1: record from the same review

Form 1 comes from the review. The user does not type shared identity, pregnancy,
death, facility or reporting data again. Form 1 is a separate document. It is not
another set of Form 4 answers.

## Shared data

The app reads these values from existing records:

| Form 1 field | Source |
|---|---|
| Name of deceased | `Patient.name` |
| Age | `Patient.age` |
| MCTS ID | `Patient.mcts_no` |
| Mobile number | `Patient.phone` |
| Current residence | `Form1.current_residence`, else `Patient.address` |
| District | `Form1.district`, else `Facility.district` |
| Date and time of death | `Death.died_at` |
| Place of death detail | `Form1.place_detail`, else `Death.place` |
| Place of death category | `Form1.place_type`. The place text is a hint only. |
| Reporting person | `Form1.reported_by_name`, else the review author |
| When death occurred | An explicit `Form1` answer. Recorded times are a hint only. |

## Data entered once

`Form1` has a one-to-one link to the review. It holds only fields that Form
4 does not have:

- state, block and village.
- husband and father names.
- native place.
- structured place of death.
- reporting person and designation.
- date of report.
- ANM name, sub-centre and verification date.
- explicit answers for the four “when did death occur” flags.

The author fills these in the **Form 1 details** panel in the review
workspace. The panel shows while the review is a draft or returned. It also shows
a count of fields that are not recorded.

## Suggested time of death

The form gives hints. It does not record an answer for the clinician.

- **During pregnancy**: the death is before delivery or outcome, or the outcome is
  “death undelivered”.
- **Within 42 days after delivery**: a delivery exists and the death is 0 to 42
  days later.
- **During abortion or within 6 weeks after abortion**: the outcome is abortion or
  ectopic and the death is within 42 days of the outcome.
- **During delivery**: the app does not infer this from a clock comparison. The
  answer stays blank until the clinician confirms it.

The app returns hints in a separate `suggested` map, not in `values`. The edit page
shows them beside the control, for example “suggested: Yes”. The input stays
blank until the user chooses.

If the user prints before choosing, the print copy shows tick boxes: Yes, No and
all place-of-death options. It does not print an invented answer. If a date is
missing, the app gives no hint.

## Output and editability

- Form 1 is a live record. The app builds it from current patient,
  pregnancy, death, facility and Form 1 records each time the page opens.
- The review version payload keeps a `form1` snapshot at submit and amendment
  submit for audit. The Form 1 page does not use it as a lock.
- The Form 1 page is an inline form. It stays editable after Form 4 is submitted
  or approved. The user can fill missing fields later.
- Changes autosave on edit. Each save increments `edit_revision` and
  `last_saved_at`, and writes a `form1_updated` audit event. The app has
  no Save button.
- `POST /review/<pk>/form1/save/?ajax=1` returns JSON. Without `?ajax=1`, it
  redirects as before.
- Form 4 stays frozen. Editing Form 1 does not change a Form 4 answer or a frozen
  version.

Form 1 links appear at:

- `/`: each review row.
- `/review/<pk>/`: the header and the section nav while drafting.
- `/review/<pk>/output/`: the output page.
- `/review/<pk>/form1/`: the edit form.
- `/review/<pk>/form1/?format=json`: JSON form.
- `/review/<pk>/form1/save/`: POST target.

## Print

- **Print** calls `window.print()` on the edit page. The app does not open a new
  tab or a new page.
- A hidden print-only copy of the form is on the page. Print CSS hides the editor,
  header and screen hints. It shows the print copy with current values.
- Before the dialog opens, the app copies the current inputs to the print copy. An
  edit prints even if autosave has not finished.
- Incomplete forms can print. Missing text and date values show blank ruled lines.
  Unselected yes/no and place-of-death fields show tick boxes for all options.
  “Not recorded.” and screen-only hints do not print.
- The edit page shows a screen-only note with the number of blank fields.

Access follows the review. Residents see their own or assigned reviews. FNOs see
all reviews. Other users get 404.

## Limits

- This is not a replacement for the signed paper Form 1.
- It is not a primary-informant or ANM workflow. It prints from the review after
  the event.
- It does not decide the legal or clinical “when death occurred” class. The
  clinician confirms it.
- It is not a Form 4 section. The Form 4 registry still has 99 fields.

## Tests

`tests/test_form1.py` covers:

- field mapping from patient, death and facility.
- place category hints.
- derived occurrence flags.
- output rendering and scoping.
- Form 1 save and audit.
- the audit snapshot at submit.
- Form 1 staying live after approval.
- edit and audit from the Form 1 page.
- AJAX autosave.
- hints that do not prefill answers.
- print copy, blank fields and tick boxes.
- author-only workspace panel and JSON output.
