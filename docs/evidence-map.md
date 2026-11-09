# Evidence map: LCG alerts beside Form 4 fields

The LCG ALERT column is a clinical interpretation. It lives in code
(`review/thresholds.py`). The version is `lcg_2021@1`. It cites the chart. The app
computes crossings from immutable observations when needed. It does not store
them. A stored alert would become a second truth. That truth could drift from the
source reading.

A crossing is evidence. It is never an answer. It does not fill a Form 4 field.
The app does not infer a field from it. The clinician makes the choice.

## Links

| LCG row | Form 4 field | Why the link is valid |
|---|---|---|
| systolic and diastolic | 4.c complications, 6 primary diagnosis | The complication list includes hypertensive disease. These readings support that judgement. |
| urine protein | 4.c, 6 | Proteinuria supports pre-eclampsia. It is not the diagnosis. |
| FHR, baseline and decelerations | 4.g neonatal outcome, 4.h probable cause | Fetal monitoring is the labour evidence for the baby's condition. |
| amniotic fluid: thick meconium or blood | 4.g, 4.h | This is also evidence for the baby's condition. |
| caput and moulding +++ | 4.g, 4.h | This can show obstructed labour. It relates to the baby's outcome. |
| contractions, duration and cervical lag | 4.c, 4.d mode | Labour progress is a common reason for operative delivery. |
| temperature and pulse | 4.c, 6 | These signs can support an infective cause. They do not prove it. |
