"""The Form 4 registry: every answer position, once.

A field owns one answer slot. A repeating block (referral, neonatal, transfusion,
interventions) is one ReviewItem whose value_json is a list of rows; its cells are
addressed ``field_key#row_index`` and are never separate ReviewItems.

Key grammar: ``f4.<section_key>.<label>``. Never the printed number, because the
form repeats 1-4 then 2-10 and splits printed 2, 3 and 4 across two sections each.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

SLUG = re.compile(r"^[a-z][a-z0-9_]*$")

#: section_key -> printed heading. Order is the printed order.
SECTIONS: dict[str, str] = {
    "background": "Background",
    "timing": "1. Timing a-g",
    "admission": "2. On admission",
    "condition": "3. Condition on admission + referral",
    "diagnosis": "4. Diagnosis at admission",
    "abortion": "2. Abortion",
    "antenatal_care": "3. Antenatal care",
    "delivery": "4. Delivery, puerperium and neonatal",
    "interventions": "5. Interventions",
    "primary_diagnosis": "6. Primary diagnosis",
    "cause_of_death": "7. Cause of death",
    "factors": "8. Factors present",
    "autopsy": "9. Autopsy",
    "summary": "10. Case summary",
}

CATEGORIES: dict[int, str] = {
    1: "Patient info and admin records",
    2: "Clinical and OBS information",
    3: "Mx and interventions",
    4: "Death ix and review",
}

HANDLING = ("propose", "derive", "prompt", "manual", "evidence")


@dataclass(frozen=True)
class Field:
    key: str
    section: str
    label_printed: str
    type: str  # text | int | bool | datetime | duration | enum
    category: int  # 1-4, per Dr Atter's framework
    handling: str = "manual"
    source: str = "clinician"  # lcg | patient_record | admin | admission | delivery | death | neonate | pregnancy | clinician
    required: bool = False
    applicability: str | None = None
    rule: str | None = None
    terminology_note: str = "same"
    precision_note: str = "same"
    options: tuple[str, ...] = field(default_factory=tuple)

    @property
    def slug(self) -> str:
        return self.key.split(".", 2)[2]


class Registry:
    def __init__(self) -> None:
        self._fields: dict[str, Field] = {}

    def add(self, f: Field) -> Field:
        if f.section not in SECTIONS:
            raise ValueError(f"{f.key}: unknown section {f.section!r}")
        expected = f"f4.{f.section}.{f.slug}"
        if f.key != expected:
            raise ValueError(f"{f.key}: key must be {expected!r}")
        if not SLUG.match(f.slug):
            raise ValueError(f"{f.key}: bad slug")
        if f.category not in CATEGORIES:
            raise ValueError(f"{f.key}: category must be 1-4")
        if f.handling not in HANDLING:
            raise ValueError(f"{f.key}: bad handling {f.handling!r}")
        if f.key in self._fields:
            raise ValueError(f"{f.key}: duplicate")
        self._fields[f.key] = f
        return f

    def __getitem__(self, key: str) -> Field:
        return self._fields[key]

    def __contains__(self, key: object) -> bool:
        return key in self._fields

    def all(self) -> list[Field]:
        return list(self._fields.values())

    def by_section(self) -> list[tuple[str, str, list[Field]]]:
        out = []
        for section, heading in SECTIONS.items():
            fields = [f for f in self._fields.values() if f.section == section]
            if fields:
                out.append((section, heading, fields))
        return out


registry = Registry()
add = registry.add


def F(key: str, section: str, label: str, type: str, category: int, **kw) -> Field:
    return add(
        Field(
            key=f"f4.{section}.{key}",
            section=section,
            label_printed=label,
            type=type,
            category=category,
            **kw,
        )
    )


# --- Background (category 1) -------------------------------------------------
F("facility_name", "background", "Name of health facility", "text", 1,
  handling="propose", source="admin", rule="f4.background.facility_name.from_facility")
F("facility_type", "background", "Type of health facility", "text", 1, handling="prompt")
F("facility_address", "background", "Address", "text", 1)
F("fbmdr_no", "background", "FBMDR No. (specific to the place)", "text", 1,
  handling="propose", source="admin", rule="f4.background.fbmdr_no.from_review")
F("mcts_no", "background", "MCTS No.", "text", 1,
  handling="propose", source="patient_record", rule="f4.background.mcts_no.from_patient",
  precision_note="MCTS is not recorded on the LCG")
F("name", "background", "Full name of deceased mother", "text", 1,
  handling="propose", source="patient_record", rule="f4.background.name.from_patient")
F("age", "background", "Age", "int", 1, handling="propose",
  source="patient_record", rule="f4.background.age.from_patient")
F("inpatient_no", "background", "Inpatient No.", "text", 1, handling="propose",
  source="admin", rule="f4.background.inpatient_no.from_admission")
F("medico_legal", "background", "Medico-legal admission", "enum", 1,
  handling="propose", source="admin", rule="f4.background.medico_legal.from_admission",
  options=("yes", "no"))
F("contact", "background", "Contact / mobile No.", "text", 1)

# --- Timing (category 2) -----------------------------------------------------
F("a", "timing", "1.a Date and time of admission", "datetime", 2,
  handling="propose", source="admission", rule="f4.timing.a.from_admission")
F("b", "timing", "1.b Date and time of death", "datetime", 2,
  handling="propose", source="death", rule="f4.timing.b.from_death")
F("c", "timing", "1.c Duration of hospital stay", "duration", 2,
  handling="derive", source="admission", rule="f4.timing.c.admission_to_exit")
F("d", "timing", "1.d Duration of ICU stay, if any", "duration", 2,
  handling="derive", source="admission", rule="f4.timing.d.icu_total")
F("e", "timing", "1.e Admission - delivery interval", "duration", 2,
  handling="derive", source="delivery", rule="f4.timing.e.admission_to_delivery")
F("f", "timing", "1.f Admission - death interval", "duration", 2,
  handling="derive", source="death", rule="f4.timing.f.admission_to_death")
F("g", "timing", "1.g Outcome of pregnancy", "enum", 2, handling="propose",
  source="pregnancy", rule="f4.timing.g.from_pregnancy",
  options=("abortion", "ectopic", "live_birth", "still_birth", "undelivered"))

# --- On admission (category 2) ----------------------------------------------
F("complaints", "admission", "2.a Complaints at time of admission", "text", 2)
F("gravida", "admission", "2.b Gravida", "int", 2)
F("para", "admission", "2.b Para", "int", 2, handling="propose",
  source="lcg", rule="f4.admission.para.from_lcg",
  terminology_note="LCG records parity as births after viability",
  precision_note="LCG has no abortions or living children")
F("abortions", "admission", "2.b Abortions", "int", 2)
F("living_children", "admission", "2.b No. of living children", "int", 2)
F("gestation", "admission", "2.c Period of gestation", "enum", 2,
  options=("before_22", "22_34", "34_plus", "intrapartum", "postpartum_24h",
           "postnatal_1w", "postnatal_42d"))

# --- Delivery (category 2 clinical; mode is category 3) ----------------------
F("labour_pains", "delivery", "4.a Did she have labour pains", "enum", 2,
  handling="propose", source="lcg", rule="f4.delivery.labour_pains.from_lcg", options=("yes", "no"))
F("partograph_used", "delivery", "4.b Was a partograph used", "enum", 2,
  options=("yes", "no", "unknown"),
  terminology_note="form asks about a partograph; the LCG is not one",
  precision_note="instrument identity preserved, never auto-converted")
F("complications", "delivery", "4.c Complications during labour", "text", 2)
F("mode", "delivery", "4.d Mode of delivery", "enum", 3,
  handling="propose", source="delivery", rule="f4.delivery.mode.from_delivery",
  options=("normal", "assisted", "breech", "caesarean", "laparotomy", "undelivered"))
F("phase", "delivery", "4.f Phase of labour at complication", "enum", 2,
  options=("first", "second", "third", "post_birth"))
F("neonatal_outcome", "delivery", "4.g Neonatal outcome", "enum", 2,
  handling="propose", source="neonate", rule="f4.delivery.neonatal.from_neonate",
  options=("alive", "fresh_still_birth", "macerated_still_birth", "neonatal_death"))
F("postnatal", "delivery", "4.i Postnatal period", "text", 2)

# --- Interventions (category 3) ---------------------------------------------
# The form's matrix is phases x procedures. Oxytocin and IV fluids are charted on
# the LCG but are not Form 4 intervention items -- reconciliation caught that.
F("performed", "interventions", "5. Interventions (phase x procedure matrix)", "block", 3,
  terminology_note="five phases by twelve procedures; transfusion carries component and units",
  precision_note="presence per cell, not dose")

# --- Death investigation and review (category 4) ----------------------------
F("dx", "primary_diagnosis", "6. Primary diagnosis / condition leading to death",
  "text", 4, required=True)
F("a_antecedent", "cause_of_death",
  "7. Part 1 a. Due to or as a consequence of", "text", 4, required=True)
F("b_antecedent", "cause_of_death",
  "7. Part 1 b. Due to or as a consequence of", "text", 4)
F("c_antecedent", "cause_of_death",
  "7. Part 1 c. Due to or as a consequence of", "text", 4)

# 8. Factors present: a fixed list, each yes / no / not known. Not a repeating
# block -- the rows are fixed by the form, not by the data.
for _key, _label in [
    ("delay_seeking_help", "Delay in woman seeking help"),
    ("refusal_treatment", "Refusal of treatment or admission"),
    ("refusal_previous_facility", "Refusal of admission in previous facility"),
    ("transport_from_home", "Lack of transport from home to health care facility"),
    ("transport_between_facilities", "Lack of transport between health care facilities"),
    ("referral_system", "Lack of assured referral system"),
    ("facilities_equipment", "Lack of facilities, equipment or consumable"),
    ("facilities_blood", "Lack of blood / blood products"),
    ("facilities_ot", "Lack of OT availability"),
    ("human_resources", "Lack of human resources"),
    ("anaesthetist", "Lack of Anaesthetist"),
    ("obstetricians", "Lack of Obstetricians"),
    ("expertise", "Lack of expertise, training or education"),
]:
    F(_key, "factors", f"8. {_label}", "enum", 4, options=("yes", "no", "not_known"))

F("performed", "autopsy", "9. Autopsy performed", "enum", 4, options=("yes", "no"))
F("diagnosis", "autopsy", "9. Autopsy final diagnosis", "text", 4)
F("text", "summary", "10. Case summary", "text", 4)
F("mo_name", "summary", "Form filled by the MO on duty - name", "text", 1)
F("fno_name", "summary", "Nodal Officer - name", "text", 1)


KEY_RE = re.compile(r"^f4\.(?P<section>[a-z_]+)\.(?P<slug>[a-z][a-z0-9_]*)$")


def parse_key(key: str) -> tuple[str, str]:
    """Split a field key into (section, slug). Raises on anything else."""
    m = KEY_RE.match(key)
    if not m:
        raise ValueError(f"bad field key: {key!r}")
    return m.group("section"), m.group("slug")


def split_cell(key: str) -> tuple[str, int | None]:
    """``f4.condition.referral.time_to_reach#2`` -> (block field key, 2)."""
    if "#" in key:
        base, _, idx = key.partition("#")
        return base, int(idx)
    return key, None
