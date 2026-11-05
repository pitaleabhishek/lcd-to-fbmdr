# Evidence map — LCG crossings shown beside Form 4 fields

The LCG's ALERT column is clinical interpretation, so it lives in code
(`review/thresholds.py`), versioned as `lcg_2021@1` and citing the chart. Crossings
are **computed from immutable observations** on demand. Nothing is stored: a stored
alert would become a second truth that can drift from the reading it came from.

A crossing is **evidence, never an answer**. It never fills a Form 4 field, and no
field is inferred from it. The clinician still chooses.

## Edges

| LCG row | Form 4 field | Why it is legitimate |
|---|---|---|
| systolic / diastolic | 4.c complications · 6 primary diagnosis | The complication list includes hypertensive disease; these are the readings behind that judgement. |
| urine protein | 4.c · 6 | Proteinuria is evidence for pre-eclampsia, not the diagnosis. |
| FHR / baseline / decelerations | 4.g neonatal outcome · 4.h probable cause | Fetal monitoring is the only labour evidence bearing on the baby's condition. |
| amniotic fluid (thick meconium, blood) | 4.g · 4.h | Same. |
| caput / moulding +++ | 4.g · 4.h | Sign of obstructed labour, relevant to the baby's outcome. |
| contractions / duration / cervical lag | 4.c (prolonged, obstructed) · 4.d mode | Labour progress is the usual reason for operative delivery. |
| temperature / pulse | 4.c (sepsis) · 6 | Signs that may support an infective cause; they do not establish it. |

## Deliberately no evidence

| Form 4 field | Why |
|---|---|
| 7. Cause of death (a–c) | A conclusion, not an observation; the LCG cannot support the wording. |
| 8. Factors present | Delay factors are about the system and the family, not labour physiology. |
| 10. Case summary | Narrative judgement. |
| 9. Autopsy | Different investigation entirely. |
| ANC, referral, abortion | Not recorded on the LCG. |
| Supportive-care alerts (no companion, supine, no oral fluid) | Quality-of-care signals with no Form 4 destination; they show on the labour record only. |

## False friends

Barred as edges, even though they look tempting:

- lag alert → "prolonged labour" (evidence, not the answer)
- BP / proteinuria → "eclampsia" (evidence, not the diagnosis)
- oxytocin → a ticked intervention (charted medicine is not a performed procedure)
- FHR deceleration → "birth asphyxia" (a cause the clinician assigns)
- no companion → a "delay" factor (not the same thing)

This table is provisional and should be confirmed by a clinician; it is the same
kind of judgement as the four overlap categories in the brief.
