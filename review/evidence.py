"""Which Form 4 fields may show which LCG evidence.

Deliberately small. An edge exists only where the Form 4 question is about the same
physiological thing the LCG row measures. Everything else — cause-of-death prose,
delay factors, autopsy, summary, ANC, referral, abortion — has no LCG evidence and
must not pretend to. See docs/evidence-map.md.
"""

from __future__ import annotations

#: form field key -> (lcg variable keys, one-sentence reason)
EVIDENCE: dict[str, tuple[tuple[str, ...], str]] = {
    "f4.delivery.complications": (
        (
            "systolic_bp", "diastolic_bp", "urine_protein",
            "contractions", "contraction_duration", "cervix",
            "temperature", "pulse",
        ),
        "The form's complication list includes hypertensive disease, prolonged or "
        "obstructed labour and sepsis; these rows are the observations behind them.",
    ),
    "f4.primary_diagnosis.dx": (
        ("systolic_bp", "diastolic_bp", "urine_protein", "temperature", "pulse"),
        "A condition leading to death may be supported by these readings; the "
        "diagnosis itself is still the clinician's.",
    ),
    "f4.delivery.neonatal_outcome": (
        ("fhr", "baseline_fhr", "fhr_deceleration", "amniotic_fluid", "caput", "moulding"),
        "Fetal monitoring is the only labour evidence bearing on how the baby was born.",
    ),
    "f4.delivery.neonatal_cause": (
        ("fhr", "baseline_fhr", "fhr_deceleration", "amniotic_fluid", "caput", "moulding"),
        "Same observations, used when the clinician assigns a probable cause of death.",
    ),
    "f4.delivery.mode": (
        ("cervix", "contractions", "contraction_duration"),
        "Labour progress is the usual reason for an operative delivery; it does not "
        "choose the mode.",
    ),
}

#: Form 4 fields with no LCG evidence at all, stated rather than left implicit.
NO_EVIDENCE = (
    "f4.cause_of_death.a_antecedent",
    "f4.cause_of_death.b_antecedent",
    "f4.cause_of_death.c_antecedent",
    "f4.factors.delay_seeking_help",
    "f4.summary.text",
    "f4.autopsy.performed",
)
