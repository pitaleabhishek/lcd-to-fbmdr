"""Form 4 (FBMDR) registry: every printed position, once.

Mirrors the LCG model: sections are ordered, fields carry type/options/required,
and repeating groups are declared as block schemas rather than free JSON.

Key grammar: ``f4.<section_key>.<label>``. Never the printed number, because the
form repeats 1-4 then 2-10 and splits printed 2, 3 and 4 across two sections.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

SLUG = re.compile(r"^[a-z][a-z0-9_]*$")

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
    "summary": "10. Case summary and sign-off",
}

CATEGORIES: dict[int, str] = {
    1: "Patient info and admin records",
    2: "Clinical and OBS information",
    3: "Mx and interventions",
    4: "Death ix and review",
}

HANDLING = ("propose", "derive", "prompt", "manual", "evidence")
TYPES = ("text", "int", "bool", "datetime", "date", "duration", "enum", "multi", "block")


@dataclass(frozen=True)
class Field:
    key: str
    section: str
    label_printed: str
    type: str
    category: int
    handling: str = "manual"
    source: str = "clinician"
    required: bool = False
    applicability: str | None = None
    rule: str | None = None
    terminology_note: str = "same"
    precision_note: str = "same"
    options: tuple[str, ...] = field(default_factory=tuple)
    block_schema: dict | None = None
    widget: str = ""  # presentation only: month | year

    @property
    def slug(self) -> str:
        return self.key.split(".", 2)[2]


class Registry:
    def __init__(self) -> None:
        self._fields: dict[str, Field] = {}

    def add(self, f: Field) -> Field:
        if f.section not in SECTIONS:
            raise ValueError(f"{f.key}: unknown section {f.section!r}")
        if f.key != f"f4.{f.section}.{f.slug}":
            raise ValueError(f"{f.key}: key must be f4.{f.section}.{f.slug}")
        if not SLUG.match(f.slug):
            raise ValueError(f"{f.key}: bad slug")
        if f.category not in CATEGORIES:
            raise ValueError(f"{f.key}: category must be 1-4")
        if f.handling not in HANDLING:
            raise ValueError(f"{f.key}: bad handling {f.handling!r}")
        if f.type not in TYPES:
            raise ValueError(f"{f.key}: bad type {f.type!r}")
        if f.type in ("enum", "multi") and not f.options:
            raise ValueError(f"{f.key}: {f.type} needs options")
        if f.type == "block" and not f.block_schema:
            raise ValueError(f"{f.key}: block needs a schema")
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


YESNO = ("yes", "no")
YNU = ("yes", "no", "unknown")

# --- Background (17) ---------------------------------------------------------
F("facility_name", "background", "Name of health facility", "text", 1,
  handling="propose", source="admin", rule="f4.background.facility_name.from_facility")
F("facility_type", "background", "Type of health facility", "text", 1, handling="prompt")
F("facility_address", "background", "Address", "text", 1)
F("nodal_name", "background", "Name of Nodal Person", "text", 1)
F("nodal_contact", "background", "Nodal contact No.", "text", 1)
F("fbmdr_no", "background", "FBMDR No. (specific to the place)", "text", 1,
  handling="propose", source="admin", rule="f4.background.fbmdr_no.from_review")
F("mcts_no", "background", "MCTS No.", "text", 1,
  handling="propose", source="patient_record", rule="f4.background.mcts_no.from_patient",
  precision_note="MCTS is not recorded on the LCG")
F("fbmdr_month", "background", "Month", "int", 1, widget="monthpicker")
F("fbmdr_year", "background", "Year", "int", 1, widget="readonly")
F("name", "background", "Full name of deceased mother", "text", 1,
  handling="propose", source="patient_record", rule="f4.background.name.from_patient")
F("age", "background", "Age", "int", 1, handling="propose", source="patient_record",
  rule="f4.background.age.from_patient")
F("inpatient_no", "background", "Inpatient No.", "text", 1, handling="propose",
  source="admin", rule="f4.background.inpatient_no.from_admission")
F("medico_legal", "background", "Medico-legal admission", "enum", 1,
  handling="propose", source="admin", rule="f4.background.medico_legal.from_admission",
  options=YESNO)
F("address", "background", "Complete address", "text", 1)
F("contact", "background", "Contact / mobile No.", "text", 1)
F("education", "background", "Education", "enum", 1,
  options=("illiterate", "upto_5th", "6th_to_12th", "beyond_12th"))
F("bpl", "background", "Below Poverty Line", "enum", 1,
  options=("bpl_certified", "self_certified", "not_bpl"))

# --- Timing (7) --------------------------------------------------------------
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

# --- On admission (6) --------------------------------------------------------
F("complaints", "admission", "2.a Complaints at time of admission", "text", 2)
F("gravida", "admission", "2.b Gravida", "int", 2)
F("para", "admission", "2.b Para", "int", 2, handling="propose", source="lcg",
  rule="f4.admission.para.from_lcg",
  terminology_note="LCG records parity as births after viability",
  precision_note="LCG has no abortions or living children")
F("abortions", "admission", "2.b Abortions", "int", 2)
F("living_children", "admission", "2.b No. of living children", "int", 2)
F("gestation", "admission", "2.c Period of gestation", "enum", 2,
  options=("before_22", "22_34", "34_plus", "intrapartum", "postpartum_24h",
           "postnatal_1w", "postnatal_42d"))

# --- Condition + referral (4) ------------------------------------------------
F("status", "condition", "3. Condition on admission", "enum", 2,
  options=("stable", "semi_conscious_verbal", "semi_conscious_painful",
           "unconscious", "brought_dead"))
F("referred", "condition", "3.a Referred from outside", "enum", 2, options=YESNO)
F("places", "condition", "3.a.i No. of places visited prior", "int", 2)

REFERRAL_SCHEMA = {
    "fields": {
        "place": {"type": "enum", "required": True,
                  "options": ["home_village", "facility_1", "facility_2", "facility_3"]},
        "date": {"type": "datetime"},
        "onset_at": {"type": "datetime"},
        "transport_call_at": {"type": "datetime"},
        "transport": {"type": "text"},
        "time_to_reach": {"type": "int", "min": 0},
        "money_transport": {"type": "number", "min": 0},
        "facility": {"type": "text"},
        "attended_by": {"type": "enum",
                        "options": ["doctor", "nurse", "other_staff", "none"]},
        "reason": {"type": "text"},
        "referral_slip": {"type": "enum", "options": ["given", "not_given"]},
        "treatment": {"type": "text"},
        "money_treatment": {"type": "number", "min": 0},
        "time_in_facility": {"type": "int", "min": 0},
    },
    "max_rows": 4,
}
F("referral", "condition", "3.b Referral table (13 attributes per place)", "block", 2,
  block_schema=REFERRAL_SCHEMA,
  terminology_note="one printed row per place; the model stores one row per place",
  precision_note="time_to_reach and time_in_facility are minutes")

# --- Diagnosis at admission (1 block) ---------------------------------------
DIAGNOSIS_SCHEMA = {
    "fields": {
        "category": {"type": "enum", "required": True,
                     "options": ["haemorrhage", "hypertensive", "labour_related",
                                 "medical", "infection", "incidental", "other"]},
        "detail": {"type": "text"},
        "underlying_cause": {"type": "text"},
    },
    "max_rows": 10,
}
F("rows", "diagnosis", "4. Diagnosis table (diagnosis + underlying cause)", "block", 2,
  block_schema=DIAGNOSIS_SCHEMA,
  terminology_note="seven printed diagnosis groups, one row each",
  precision_note="underlying cause is free text, as printed")

# --- Abortion (7) ------------------------------------------------------------
F("type", "abortion", "2.a Spontaneous / Induced", "enum", 2,
  options=("spontaneous", "induced"))
F("spontaneous_type", "abortion", "2.a.i Complete / Incomplete", "enum", 2,
  options=("complete", "incomplete"), applicability="spontaneous")
F("induced_legality", "abortion", "2.a.ii Legal / Illegal", "enum", 2,
  options=("legal", "illegal"), applicability="induced")
F("procedure", "abortion", "2.b Procedure adopted", "enum", 2,
  options=("medical", "mva", "d_and_e", "extra_amniotic", "hysterotomy", "other"))
F("post_abortal", "abortion", "2.c Post-abortal period", "enum", 2,
  options=("uneventful", "sepsis", "haemorrhage", "other"))
F("multiple_centres", "abortion", "2.d Procedure in more than one centre", "enum", 2,
  options=YESNO)
F("centres", "abortion", "2.d Centres visited", "text", 2,
  applicability="multiple_centres")

# --- Antenatal care (7) ------------------------------------------------------
F("received", "antenatal_care", "3.a Did she receive ANC", "enum", 2, options=YNU)
F("facility", "antenatal_care", "3.b Type of facility", "enum", 2,
  options=("sc", "phc", "chc", "sdh", "dh", "medical_college", "private", "other"))
F("facility_other", "antenatal_care", "3.b Other facility, specify", "text", 2,
  applicability="other")
F("provider", "antenatal_care", "3.c Services provided by", "enum", 2,
  options=("anm", "mo", "obstetrician", "ayush", "nurse", "other_specialist"))
F("provider_other", "antenatal_care", "3.c Other specialist, specify", "text", 2,
  applicability="other_specialist")
F("counselled", "antenatal_care", "3.d Told about a disorder / complication", "enum", 2,
  options=YNU)
F("risks", "antenatal_care", "3.e Risk factor identified", "multi", 2,
  options=("abortion", "ectopic", "vesicular_mole", "aph", "hydramnios_oligohydramnios",
           "short_stature", "pih_pe", "previous_cs", "multiple_pregnancy",
           "grand_multi", "abnormal_presentation", "big_baby", "anaemia",
           "diabetes_gdm", "medical_conditions", "others"))

# --- Delivery, puerperium, neonatal (17) ------------------------------------
F("labour_pains", "delivery", "4.a Did she have labour pains", "enum", 2,
  handling="propose", source="lcg", rule="f4.delivery.labour_pains.from_lcg",
  options=YESNO)
F("partograph_past", "delivery", "4.b.i Partograph used - past facility", "enum", 2,
  options=YNU)
F("partograph_current", "delivery", "4.b.ii Partograph used - current facility", "enum", 2,
  options=YESNO,
  terminology_note="form asks about a partograph; the LCG is not one",
  precision_note="instrument identity preserved, never auto-converted")
F("complications", "delivery", "4.c Complications during labour", "multi", 2,
  options=("prolonged_labour", "obstructed_labour_rupture", "diabetes_gdm",
           "eclampsia_pre_eclampsia", "inversion_uterus", "intrapartum_haemorrhage",
           "ip_sepsis", "others"))
F("complications_other", "delivery", "4.c Others, specify", "text", 2)
F("mode", "delivery", "4.d Mode of delivery", "enum", 3,
  handling="propose", source="delivery", rule="f4.delivery.mode.from_delivery",
  options=("undelivered", "normal", "normal_with_episiotomy", "forceps", "vacuum",
           "breech", "multiple_pregnancy", "caesarean_elective",
           "caesarean_emergency", "laparotomy", "ectopic"))
F("mode_indication", "delivery", "4.d Indication (CS / instrumental)", "text", 3)
F("anaesthesia", "delivery", "4.e Anaesthesia", "multi", 3,
  options=("general", "epidural_spinal", "local"))
F("anaesthesia_reaction", "delivery", "4.e Any adverse reaction", "text", 3)
F("phase", "delivery", "4.f Phase of labour at complication", "enum", 2,
  options=("first", "second", "third", "post_birth"))
F("neonatal_outcome", "delivery", "4.g Neonatal outcome", "enum", 2,
  handling="propose", source="neonate", rule="f4.delivery.neonatal.from_neonate",
  options=("alive", "fresh_still_birth", "macerated_still_birth", "neonatal_death"))
F("neonatal_death_time", "delivery", "4.h Time of neonatal death", "enum", 2,
  options=("lt_6h", "6_to_24h", "gt_24h"), applicability="neonatal_death")
F("neonatal_cause", "delivery", "4.h Probable cause of neonatal death", "multi", 2,
  options=("birth_asphyxia", "respiratory_distress", "aspiration_mas", "sepsis",
           "congenital_anomalies", "preterm", "others"))
F("neonatal_cause_other", "delivery", "4.h Others, specify", "text", 2)
F("postnatal", "delivery", "4.i Postnatal period", "enum", 2,
  options=("uneventful", "eventful"))
F("postnatal_cause", "delivery", "4.i Probable cause if eventful", "multi", 2,
  options=("pph", "pe_eclampsia", "cva_pulmonary_embolism", "sepsis_ards",
           "anaemia", "post_op_complication", "medical_conditions", "others"))
F("postnatal_cause_other", "delivery", "4.i Others, specify", "text", 2)

# --- Interventions (5) -------------------------------------------------------
INTERVENTION_SCHEMA = {
    "fields": {
        "phase": {"type": "enum", "required": True,
                  "options": ["early_pregnancy", "antenatal", "intrapartum",
                              "postpartum", "anaesthesia_icu"]},
        "procedure": {"type": "enum", "required": True,
                      "options": ["evacuation", "transfusion", "laparotomy_laparoscopy",
                                  "hysterectomy", "version", "other_surgery",
                                  "instrumental_delivery", "caesarean_section",
                                  "manual_removal_placenta", "conservative_surgery",
                                  "removal_retained_poc", "anaesthesia", "icu_monitoring"]},
        "note": {"type": "text"},
    },
    "max_rows": 60,
}
F("matrix", "interventions", "5. Interventions matrix (phase x procedure)", "block", 3,
  block_schema=INTERVENTION_SCHEMA,
  terminology_note="five phases by twelve procedures",
  precision_note="presence per cell, not dose")
F("transfusion_given", "interventions", "5. Blood transfusion given", "enum", 3,
  options=YESNO)
F("transfusion_units", "interventions", "5. No. of units", "int", 3,
  applicability="transfusion_given")
F("transfusion_components", "interventions", "5. If yes, No of units (Cryo / Whole Blood / PRBC / FFP / Platelets)", "multi", 3,
  options=("cryo", "whole_blood", "prbc", "ffp", "platelets"))
F("transfusion_reaction", "interventions", "5. Transfusion reaction", "enum", 3,
  options=YESNO)

# --- Death investigation and review (19) ------------------------------------
F("dx", "primary_diagnosis", "6. Primary diagnosis / condition leading to death",
  "text", 4, required=True)
F("a_antecedent", "cause_of_death",
  "7. Part 1 a. Due to or as a consequence of", "text", 4, required=True)
F("b_antecedent", "cause_of_death",
  "7. Part 1 b. Due to or as a consequence of", "text", 4)
F("c_antecedent", "cause_of_death",
  "7. Part 1 c. Due to or as a consequence of", "text", 4)

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

F("performed", "autopsy", "9. Autopsy performed", "enum", 4, options=YESNO)
F("diagnosis", "autopsy", "9. Autopsy final diagnosis", "text", 4)
F("text", "summary", "10. Case summary", "text", 4)
F("mo_name", "summary", "Form filled by the MO on duty - name", "text", 1)
F("fno_name", "summary", "Nodal Officer - name", "text", 1)
F("designation", "summary", "Designation", "text", 1)
F("institution_address", "summary", "Address of the Institution", "text", 1)
F("signed_on", "summary", "Stamp & Date", "date", 1,
  precision_note="one date for the sign-off block")


KEY_RE = re.compile(r"^f4\.(?P<section>[a-z_]+)\.(?P<slug>[a-z][a-z0-9_]*)$")


def parse_key(key: str) -> tuple[str, str]:
    m = KEY_RE.match(key)
    if not m:
        raise ValueError(f"bad field key: {key!r}")
    return m.group("section"), m.group("slug")


def split_cell(key: str) -> tuple[str, int | None]:
    """``f4.condition.referral#2`` -> (block field key, 2)."""
    if "#" in key:
        base, _, idx = key.partition("#")
        return base, int(idx)
    return key, None
