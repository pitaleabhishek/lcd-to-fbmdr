"""The WHO Labour Care Guide as data: 7 sections, 34 variables, in printed order.

Section 1 is the header (one value per chart). Sections 2-7 are observations on a
horizontal time axis. The ALERT column is a rule, not a cell, so thresholds live
here as ``alert`` and are never stored as observations.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Reconciled against the printed chart (WHO Labour Care Guide, 2021).
# Deliberately absent: urine volume (not a row on the chart) and pushing
# (a plotted "P" marker on the descent line; stage already records it).
SECTIONS = [
    (1, "identifying", "Identifying information and labour characteristics at admission"),
    (2, "supportive_care", "Supportive care"),
    (3, "baby", "Care of the baby"),
    (4, "woman", "Care of the woman"),
    (5, "progress", "Labour progress"),
    (6, "medication", "Medication"),
    (7, "shared_decision", "Shared decision-making"),
]


@dataclass(frozen=True)
class Variable:
    key: str
    section: str
    label: str
    type: str  # text | num | enum | bool | datetime
    ord: int
    unit: str = ""
    alert: str = ""
    options: tuple[str, ...] = field(default_factory=tuple)


V = Variable
VARIABLES: list[Variable] = [
    # --- 1. Identifying information and labour characteristics at admission ---
    V("name", "identifying", "Name", "text", 1),
    V("parity", "identifying", "Parity", "text", 2),
    V("labour_onset", "identifying", "Labour onset", "enum", 3,
      options=("spontaneous", "induced")),
    V("active_labour_dx", "identifying", "Active labour diagnosis", "datetime", 4),
    V("ruptured_membranes", "identifying", "Ruptured membranes", "datetime", 5),
    V("risk_factors", "identifying", "Risk factors", "text", 6),

    # --- 2. Supportive care ---
    V("companion", "supportive_care", "Companion", "enum", 1,
      options=("yes", "no", "declined")),
    V("pain_relief", "supportive_care", "Pain relief", "enum", 2,
      options=("yes", "no", "declined")),
    V("oral_fluid", "supportive_care", "Oral fluid", "enum", 3,
      options=("yes", "no", "declined")),
    V("posture", "supportive_care", "Posture", "enum", 4,
      options=("supine", "mobile", "upright", "lateral")),

    # --- 3. Care of the baby ---
    V("baseline_fhr", "baby", "Baseline", "num", 1, unit="/min",
      alert="<110 or >=160"),
    V("fhr", "baby", "FHR", "num", 2, unit="/min", alert="<110 or >=160"),
    V("fhr_deceleration", "baby", "FHR deceleration", "enum", 3,
      options=("none", "early", "late", "variable"), alert="late"),
    V("amniotic_fluid", "baby", "Amniotic fluid", "enum", 4,
      options=("intact", "clear", "meconium", "blood"), alert="meconium or blood"),
    V("fetal_position", "baby", "Fetal position", "enum", 5,
      options=("anterior", "posterior", "transverse")),
    V("caput", "baby", "Caput", "enum", 6,
      options=("0", "+", "++", "+++"), alert="+++"),
    V("moulding", "baby", "Moulding", "enum", 7,
      options=("0", "+", "++", "+++"), alert="+++"),

    # --- 4. Care of the woman ---
    V("pulse", "woman", "Pulse", "num", 1, unit="/min", alert="<60 or >=120"),
    V("systolic_bp", "woman", "Systolic BP", "num", 2, unit="mmHg", alert="<80 or >=140"),
    V("diastolic_bp", "woman", "Diastolic BP", "num", 3, unit="mmHg", alert=">=90"),
    V("temperature", "woman", "Temperature", "num", 4, unit="C", alert="<35.0 or >=37.5"),
    V("urine_protein", "woman", "Urine protein", "enum", 5,
      options=("0", "+", "++", "+++"), alert=">=++"),
    V("urine_acetone", "woman", "Urine acetone", "enum", 6,
      options=("0", "+", "++", "+++"), alert=">=++"),

    # --- 5. Labour progress ---
    V("contractions", "progress", "Contractions per 10 min", "num", 1,
      unit="/10min", alert="<=2 or >5"),
    V("contraction_duration", "progress", "Duration of contractions", "num", 2,
      unit="s", alert="<20 or >60"),
    V("cervix", "progress", "Cervix", "num", 3, unit="cm",
      alert="lag time exceeded for current dilatation"),
    V("descent", "progress", "Descent", "num", 4, unit="station"),

    # --- 6. Medication ---
    V("oxytocin", "medication", "Oxytocin", "num", 1, unit="U/L"),
    V("medicine", "medication", "Medicine", "text", 2),
    V("iv_fluids", "medication", "IV fluids", "text", 3),

    # --- 7. Shared decision-making ---
    V("assessment", "shared_decision", "Assessment", "text", 1),
    V("plan", "shared_decision", "Plan", "text", 2),
    V("initials", "shared_decision", "Initials", "text", 3),
]

HEADER_KEYS = {v.key for v in VARIABLES if v.section == "identifying"}
GRID_KEYS = [v.key for v in VARIABLES if v.section != "identifying"]

BY_KEY = {v.key: v for v in VARIABLES}
