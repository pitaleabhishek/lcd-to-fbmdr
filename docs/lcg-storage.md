# LCG storage model

How the WHO Labour Care Guide is stored. Sources: *WHO Labour Care Guide: User's
Manual* (2021) and the printed chart in `docs/`-adjacent PDFs. Nothing here is
clinical interpretation except the alert column, which is application code.

## Tables

| Table | Rows per chart | Stores |
|---|---|---|
| `review_lcgsection` | reference | the 7 printed sections: order, key, label |
| `review_lcgvariable` | reference | each printed row: key, section, label, order, type, unit, allowed values, numeric bounds, alert text |
| `review_sourcedocument` | 1 | the chart as an object: `kind=lcg`, format, author, entered_by, documented_at, received_at, entered_at, time precision, `header_json` |
| `review_observation` | one per cell | variable, stage, value, unit, observed_at, observed_at_precision, documented_at, entered_at, author, author_role, supersedes |

Two reference tables (the form), two instance tables (a filled chart). No column
entity: time columns are derived by grouping observations on `observed_at`.

```
section 1 ── N variable
document 1 ── N observation
variable 1 ── N observation
```

## How data is stored

- **One document per chart.** A labour over 12 h continues on the same document,
  with more observations; there is no continuation-sheet entity.
- **Section 1 is `header_json`** on the document: name, parity, labour onset,
  active-labour diagnosis, ruptured membranes, risk factors. These occur once per
  chart, so they are not rows on the time axis.
- **Sections 2–7 are observations.** One row per variable per time column. A
  variable charted seven times is seven rows.
- **Stage is stamped on each row** (`first` / `second`), because that is what a
  reader queries. Rows are append-only, so it cannot change after insert.
- **Three timestamps**: `observed_at` (clinical time), `documented_at` (what the
  chart says), `entered_at` (server). `author` ≠ `entered_by`; transcription never
  transfers authorship.
- **The enum value is the value.** No parsing and no second copy: `clear`, `meconium_3`, `2+`, `supine` are stored in the form's own vocabulary, and anything else is rejected by the trigger. The printed marks (`C`, `M+++`, `P 2+`) are a one-to-one reading of these codes, not a separate field.
- **Gaps are absent rows.** A missed observation is found by comparing observed
  times against the cadence a rule set requires; the paper chart's time axis is
  blank, so there is no printed empty cell to store.
- **Corrections** are a new row with `supersedes_id`. UPDATE and DELETE are
  blocked by a trigger on `observation`, `sourcedocument`, `delivery`, `death`,
  `carecontact`. The chart, the rules and the alert crossings read only the head
  of each chain (`superseded_by IS NULL`), so a corrected 150 stops firing; the
  history screen reads every row and shows both.

## Value rules

`review_lcgvariable` declares what the printed chart permits. A `BEFORE INSERT OR
UPDATE` trigger on `review_observation` rejects anything else: an enum value not in
`options`, a number outside `min_num`/`max_num`, a unit that does not match, or a
stage other than `first`/`second`. `Observation.clean()` mirrors this for form
errors. Alerts are **not** enforced here — see below.

## Alert rules

Thresholds live in application code, versioned and cited, never in SQL.

- `alert_rule` on the variable is a **display projection** of the code (the printed
  alert text), so a reader of `lcg_chart` sees it. It is never evaluated.
- Crossings are **computed** from immutable observations and shown as *computed
  evidence* beside the relevant review item. They are never stored, so they cannot
  drift from the data they came from.
- The rule set is named `lcg_2021@1`; the review version records it.

## Variables, by section

Values are canonical codes; the printed mark is in brackets. Alerts are the
printed alert column.

### 1. Identifying information and labour characteristics at admission

Header, not time series. Manual Table 2.

| Key | Values |
|---|---|
| `name` | text |
| `parity` | integer (local coding, e.g. P1) |
| `labour_onset` | `spontaneous` / `induced` |
| `active_labour_dx` | date |
| `ruptured_membranes` | date + time |
| `risk_factors` | text |

### 2. Supportive care

Manual Table 3. All three Y/N/D rows alert on `no`; posture alerts on `supine`.

| Key | Values | Alert |
|---|---|---|
| `companion` (Companionship) | `yes` / `no` / `declined` | no |
| `pain_relief` | `yes` / `no` / `declined` | no |
| `oral_fluid` | `yes` / `no` / `declined` | no |
| `posture` | `supine` / `mobile` | supine |

`mobile` includes walking, swaying, left lateral, squatting, kneeling and standing
— that is why there are only two postures.

### 3. Care of the baby

Manual Table 4. FHR in /min, 50–250.

| Key | Values | Alert |
|---|---|---|
| `baseline_fhr` | number | <110, ≥160 |
| `fhr` | number | <110, ≥160 |
| `fhr_deceleration` | `no` / `early` / `late` / `variable` | late |
| `amniotic_fluid` | `intact` / `clear` / `meconium_1` / `meconium_2` / `meconium_3` / `blood` | meconium_3, blood |
| `fetal_position` | `anterior` / `posterior` / `transverse` | posterior, transverse |
| `caput` | `0` / `+` / `++` / `+++` | +++ |
| `moulding` | `0` / `+` / `++` / `+++` | +++ |

`meconium_1/2/3` are non-significant, medium and thick meconium (`M+`, `M++`,
`M+++`). `anterior` is normal, which is why only P and T alert.

### 4. Care of the woman

Manual Table 5.

| Key | Values | Unit | Range | Alert |
|---|---|---|---|---|
| `pulse` | number | /min | 20–220 | <60, ≥120 |
| `systolic_bp` | number | mmHg | 40–300 | <80, ≥140 |
| `diastolic_bp` | number | mmHg | 20–200 | ≥90 |
| `temperature` | number | C | 30–45 | <35.0, ≥37.5 |
| `urine_protein` | `negative` / `trace` / `1+` / `2+` / `3+` / `4+` | — | — | 2+ |
| `urine_acetone` | `negative` / `trace` / `1+` / `2+` / `3+` / `4+` | — | — | 2+ |

Urine is a reagent strip, read as protein (P) and acetone (A). The printed legend
lists P–…P3+ and A–…A4+; Table 5 says record negative, trace, +, ++, +++, ++++ for
both, so both carry six values. One printed row, two variables — a cell cannot hold
two grades.

### 5. Labour progress

Manual Table 6.

| Key | Values | Unit | Range | Alert |
|---|---|---|---|---|
| `contractions` | number | /10min | 0–10 | ≤2, >5 |
| `contraction_duration` | number | s | 0–120 | <20, >60 |
| `cervix` | number | cm | 0–10 | lag time for current dilatation |
| `descent` | number | station | 0–5 | — |

Cervical lag is not a fixed threshold: 10 cm ≥2 h, 9 ≥2.5 h, 8 ≥3 h, 7 ≥5 h,
6 ≥6 h. That is a rule, not an `alert_rule` string.

### 6. Medication

Manual §6. The chart asks oxytocin as **U/L and drops/min**, so it is two rows.

| Key | Values | Unit |
|---|---|---|
| `oxytocin` | number | U/L |
| `oxytocin_drops` | number | drops/min |
| `medicine` | text (name, dose, route) | — |
| `iv_fluids` | `yes` / `no` | — |

### 7. Shared decision-making

Manual Table 8. All free text, per column.

| Key | Values |
|---|---|
| `assessment` | text |
| `plan` | text |
| `initials` | text |

## Not stored

| Chart element | Why |
|---|---|
| ALERT column | fixed guideline text; thresholds are code |
| Circled alerts | computed crossings, not annotations |
| Plot glyphs X / O / P | values are stored; glyphs are rendering |
| Urine volume | not a row on the chart |
| "Pushing" | not a row — a `P` marker on the descent line; stage records it |
| Continuation sheets | more columns on the same document |

## Views

| View | One row per |
|---|---|
| `lcg_chart` | variable, cells across time in IST |
| `lcg_cells` | cell, with computed column number and stage |
| `lcg_header` | Section 1 key/value |
