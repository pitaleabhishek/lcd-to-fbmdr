# LCG storage model

This document describes how the app stores the WHO Labour Care Guide (LCG). 

## Tables

| Table | Rows per chart | Stores |
|---|---|---|
| `review_lcgsection` | reference | The 7 printed sections: order, key and label |
| `review_lcgvariable` | reference | Each printed row: key, section, label, order, type, unit, values, numeric limits and alert text |
| `review_sourcedocument` | 1 | The chart object: `kind=lcg`, format, author, entered_by, documented_at, received_at, entered_at, time precision and `header_json` |
| `review_observation` | One for each cell | Variable, stage, value, unit, observed_at, observed_at_precision, documented_at, entered_at, author, author_role and supersedes |

Two tables hold the form. Two tables hold a filled chart. The app has no column
table. It derives time columns by grouping observations on `observed_at`.


## Data storage

- **One document for each chart.** A labour over 12 hours stays on the same
  document. The app adds observations. The app has no continuation-sheet table.
- **Section 1 is `header_json`** on the document. It holds name, parity, labour
  onset, active-labour diagnosis, ruptured membranes and risk factors. These occur
  once for each chart. They are not rows on the time axis.
- **Sections 2 to 7 are observations.** The app stores one row for each variable at
  each time column. A variable charted seven times has seven rows.
- **The app stores the stage on each row** (`first` or `second`). Rows are
  append-only. The stage cannot change after insert.
- **The app stores three timestamps.** `observed_at` is the clinical time.
  `documented_at` is the time on the chart. `entered_at` is the server time.
  `author` is not `entered_by`. Transcription does not transfer authorship.
- **The enum value is the value.** The app does not parse it and does not keep a
  second copy. Values such as `clear`, `meconium_3`, `2+` and `supine` use the
  form vocabulary. The trigger rejects any other value. Printed marks such as `C`,
  `M+++` and `P 2+` map one-to-one to these codes. They are not separate fields.
- **A gap is an absent row.** The paper chart has a blank time axis. The chart
  shows columns only for recorded times. It lists those times. It uses a dot for a
  variable that is not recorded at a column. It does not apply a
  monitoring-frequency limit and does not call an interval a clinical gap. The app
  stores nothing and creates no review answer from a missing observation.
- **A correction is a new row with `supersedes_id`.** A trigger blocks UPDATE and
  DELETE on `observation`, `sourcedocument`, `delivery`, `death` and
  `carecontact`. The chart, rules and alerts read only the current row
  (`superseded_by IS NULL`). A corrected 150 stops firing. The history screen
  reads every row and shows both.

## Value rules

`review_lcgvariable` declares what the printed chart permits. A `BEFORE INSERT OR
UPDATE` trigger on `review_observation` rejects these cases:

- an enum value is not in `options`;
- a number is outside `min_num` or `max_num`;
- the unit does not match;
- the stage is not `first` or `second`.

`Observation.clean()` repeats these checks for form errors. The trigger does not
enforce alerts.

## Alert rules

Thresholds live in application code. They have a version and a citation. They do
not live in SQL.

- `alert_rule` on the variable is a display copy of the code. It shows the printed
  alert text in `lcg_chart`. The app never evaluates it.
- The app computes crossings from immutable observations. It shows them as
  *computed evidence* beside the review item. It does not store them. They cannot
  drift from the source data.
- The rule set is `lcg_2021@1`. The review version records it.

## Variables by section

The values are canonical codes. The printed mark is in brackets. The alert column
shows the printed alert.

### 1. Admission: identity and labour characteristics

This is header data, not a time series. See Manual Table 2.

| Key | Values |
|---|---|
| `name` | text |
| `parity` | integer (local code, for example P1) |
| `labour_onset` | `spontaneous` or `induced` |
| `active_labour_dx` | date |
| `ruptured_membranes` | date and time |
| `risk_factors` | text |

### 2. Supportive care

See Manual Table 3. The three Y/N/D rows alert on `no`. Posture alerts on
`supine`.

| Key | Values | Alert |
|---|---|---|
| `companion` (Companionship) | `yes`, `no` or `declined` | no |
| `pain_relief` | `yes`, `no` or `declined` | no |
| `oral_fluid` | `yes`, `no` or `declined` | no |
| `posture` | `supine` or `mobile` | supine |

`mobile` includes walking, swaying, left lateral, squatting, kneeling and
standing. That is why there are only two postures.

### 3. Care of the baby

See Manual Table 4. FHR is in /min and ranges from 50 to 250.

| Key | Values | Alert |
|---|---|---|
| `baseline_fhr` | number | <110, ≥160 |
| `fhr` | number | <110, ≥160 |
| `fhr_deceleration` | `no`, `early`, `late` or `variable` | late |
| `amniotic_fluid` | `intact`, `clear`, `meconium_1`, `meconium_2`, `meconium_3` or `blood` | meconium_3, blood |
| `fetal_position` | `anterior`, `posterior` or `transverse` | posterior, transverse |
| `caput` | `0`, `+`, `++` or `+++` | +++ |
| `moulding` | `0`, `+`, `++` or `+++` | +++ |

`meconium_1`, `meconium_2` and `meconium_3` are non-significant, medium and thick
meconium (`M+`, `M++`, `M+++`). `anterior` is normal. That is why only P and T
alert.

### 4. Care of the woman

See Manual Table 5.

| Key | Values | Unit | Range | Alert |
|---|---|---|---|---|
| `pulse` | number | /min | 20-220 | <60, ≥120 |
| `systolic_bp` | number | mmHg | 40-300 | <80, ≥140 |
| `diastolic_bp` | number | mmHg | 20-200 | ≥90 |
| `temperature` | number | C | 30-45 | <35.0, ≥37.5 |
| `urine_protein` | `negative`, `trace`, `1+`, `2+`, `3+` or `4+` | none | none | 2+ |
| `urine_acetone` | `negative`, `trace`, `1+`, `2+`, `3+` or `4+` | none | none | 2+ |

Urine uses a reagent strip. Staff read protein (P) and acetone (A). The printed
legend lists P- to P3+ and A- to A4+. Table 5 says to record negative, trace, +,
++, +++ and ++++ for both. One printed row holds two variables. A cell cannot hold
two grades.

### 5. Labour progress

See Manual Table 6.

| Key | Values | Unit | Range | Alert |
|---|---|---|---|---|
| `contractions` | number | /10min | 0-10 | ≤2, >5 |
| `contraction_duration` | number | s | 0-120 | <20, >60 |
| `cervix` | number | cm | 0-10 | lag time for current dilatation |
| `descent` | number | station | 0-5 | none |

Cervical lag is not a fixed threshold:

- 10 cm: 2 hours or more;
- 9 cm: 2.5 hours or more;
- 8 cm: 3 hours or more;
- 7 cm: 5 hours or more;
- 6 cm: 6 hours or more.

This is a rule, not an `alert_rule` string.

### 6. Medication

See Manual section 6. The chart records oxytocin as U/L and drops/min. The app uses
two rows.

| Key | Values | Unit |
|---|---|---|
| `oxytocin` | number | U/L |
| `oxytocin_drops` | number | drops/min |
| `medicine` | text (name, dose, route) | none |
| `iv_fluids` | `yes` or `no` | none |

### 7. Shared decision-making


| Key | Values |
|---|---|
| `assessment` | text |
| `plan` | text |
| `initials` | text |

## Not stored

| Chart element | Why |
|---|---|
| ALERT column | Fixed guideline text. Thresholds are code. |
| Circled alerts | Computed crossings, not notes. |
| Plot glyphs X, O and P | The app stores values. Glyphs are rendering. |
| Urine volume | Not a chart row. |
| “Pushing” | Not a row. A `P` marker shows on the descent line. The stage records it. |
| Continuation sheets | More columns on the same document. |

## Views

| View | One row for each |
|---|---|
| `lcg_chart` | Variable, with cells across time in IST |
| `lcg_cells` | Cell, with column number and stage |
| `lcg_header` | Section 1 key and value |
