"""Domain models for LCG reuse in a Facility-Based Maternal Death Review (Form 4).

Two sides, never mixed:
  * recorded facts  -> Observation, SourceDocument, Delivery, Death, CareContact (append-only)
  * review answers  -> ReviewItem, rendered only from a ReviewVersion
Proposals are the bridge.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


class TimePrecision(models.TextChoices):
    EXACT = "exact", "Exact"
    ESTIMATED = "estimated", "Estimated"
    DATE_ONLY = "date_only", "Date only"
    UNKNOWN = "unknown", "Unknown"


class Facility(models.Model):
    name = models.CharField(max_length=200)
    level = models.CharField(max_length=50, blank=True)
    district = models.CharField(max_length=100, blank=True)
    address = models.TextField(blank=True)
    nodal_name = models.CharField(max_length=200, blank=True)
    nodal_phone = models.CharField(max_length=30, blank=True)

    def __str__(self) -> str:
        return self.name


class Patient(models.Model):
    mcts_no = models.CharField(max_length=30, blank=True)
    name = models.CharField(max_length=200)
    age = models.PositiveSmallIntegerField(null=True, blank=True)
    sex = models.CharField(max_length=10, default="female")
    address = models.TextField(blank=True)
    education = models.CharField(max_length=50, blank=True)
    bpl = models.CharField(max_length=50, blank=True)
    phone = models.CharField(max_length=30, blank=True)

    def __str__(self) -> str:
        return self.name


class Pregnancy(models.Model):
    class Outcome(models.TextChoices):
        DELIVERY = "delivery", "Live birth / delivery"
        ABORTION = "abortion", "Abortion"
        ECTOPIC = "ectopic", "Ectopic"
        UNDELIVERED = "death_undelivered", "Death undelivered"

    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name="pregnancies")
    outcome = models.CharField(max_length=20, choices=Outcome.choices, blank=True)
    outcome_at = models.DateTimeField(null=True, blank=True)
    gestation_weeks = models.PositiveSmallIntegerField(null=True, blank=True)
    gestation_days = models.PositiveSmallIntegerField(null=True, blank=True)
    risk_codes = models.JSONField(default=list, blank=True)
    risk_note = models.TextField(blank=True)
    anc_received = models.CharField(max_length=20, blank=True)
    anc_facility_type = models.CharField(max_length=50, blank=True)
    anc_provider = models.CharField(max_length=50, blank=True)
    anc_counselled = models.CharField(max_length=20, blank=True)
    anc_risks = models.JSONField(default=list, blank=True)
    abortion_detail = models.JSONField(default=dict, blank=True)
    postnatal_course = models.CharField(max_length=50, blank=True)
    postnatal_note = models.TextField(blank=True)

    def __str__(self) -> str:
        return f"Pregnancy {self.pk} ({self.patient.name})"


class Admission(models.Model):
    pregnancy = models.ForeignKey(Pregnancy, on_delete=models.PROTECT, related_name="admissions")
    facility = models.ForeignKey(Facility, on_delete=models.PROTECT)
    uin = models.CharField(max_length=50, blank=True)
    admitted_at = models.DateTimeField(null=True, blank=True)
    time_precision = models.CharField(
        max_length=20, choices=TimePrecision.choices, default=TimePrecision.EXACT
    )
    discharged_at = models.DateTimeField(null=True, blank=True)
    admitted_by = models.CharField(max_length=200, blank=True)
    medico_legal = models.CharField(max_length=20, blank=True)
    condition_on_admission = models.CharField(max_length=100, blank=True)
    complaints = models.TextField(blank=True)


class SourceDocument(models.Model):
    class Kind(models.TextChoices):
        LCG = "lcg", "WHO Labour Care Guide"
        PARTOGRAPH = "partograph", "Partograph"
        ADMISSION_NOTE = "admission_note", "Admission note"
        REFERRAL_SLIP = "referral_slip", "Referral slip"
        ANC_CARD = "anc_card", "ANC card"
        DEATH_SUMMARY = "death_summary", "Death summary"

    pregnancy = models.ForeignKey(Pregnancy, on_delete=models.PROTECT, related_name="documents")
    admission = models.ForeignKey(
        Admission, on_delete=models.PROTECT, null=True, blank=True, related_name="documents"
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    source_format = models.CharField(max_length=50, blank=True)
    origin_facility = models.CharField(max_length=200, blank=True)
    author = models.CharField(max_length=200, blank=True)
    entered_by = models.CharField(max_length=200, blank=True)
    documented_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    entered_at = models.DateTimeField(auto_now_add=True)
    time_precision = models.CharField(
        max_length=20, choices=TimePrecision.choices, default=TimePrecision.EXACT
    )
    supersedes = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="superseded_by"
    )
    note = models.TextField(blank=True)


class LCGSection(models.Model):
    """One of the seven printed sections of the WHO Labour Care Guide."""

    ord = models.PositiveSmallIntegerField(unique=True)
    key = models.CharField(max_length=50, unique=True)
    label = models.CharField(max_length=200)

    class Meta:
        ordering = ["ord"]

    def __str__(self) -> str:
        return self.label


class LCGVariable(models.Model):
    """A printed row of the LCG. The ALERT column is a rule, not a value."""

    key = models.CharField(max_length=50, unique=True)
    section = models.ForeignKey(LCGSection, on_delete=models.PROTECT, related_name="variables")
    label = models.CharField(max_length=200)
    ord = models.PositiveSmallIntegerField()
    type = models.CharField(max_length=20)
    unit = models.CharField(max_length=30, blank=True)
    alert_rule = models.CharField(max_length=200, blank=True)
    options = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["section__ord", "ord"]
        constraints = [
            models.UniqueConstraint(fields=["section", "ord"], name="uniq_lcg_section_ord")
        ]

    def __str__(self) -> str:
        return f"{self.section.label} / {self.label}"


class Observation(models.Model):
    document = models.ForeignKey(SourceDocument, on_delete=models.PROTECT, related_name="observations")
    variable = models.ForeignKey(LCGVariable, on_delete=models.PROTECT, related_name="observations")
    stage = models.CharField(
        max_length=10,
        choices=[("first", "Active first stage"), ("second", "Second stage")],
        default="first",
    )
    value_num = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    value_text = models.CharField(max_length=200, blank=True)
    value_code = models.CharField(max_length=50, blank=True)
    unit = models.CharField(max_length=30, blank=True)
    observed_at = models.DateTimeField(null=True, blank=True)
    observed_at_precision = models.CharField(
        max_length=20, choices=TimePrecision.choices, default=TimePrecision.EXACT
    )
    documented_at = models.DateTimeField(null=True, blank=True)
    entered_at = models.DateTimeField(auto_now_add=True)
    entered_by = models.CharField(max_length=200, blank=True)
    author = models.CharField(max_length=200, blank=True)
    author_role = models.CharField(max_length=50, blank=True)
    raw_label = models.CharField(max_length=200, blank=True)
    raw_value = models.CharField(max_length=200, blank=True)
    supersedes = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="superseded_by"
    )
    note = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["document", "variable", "observed_at"],
                         name="obs_doc_var_time_idx")
        ]


class CareContact(models.Model):
    pregnancy = models.ForeignKey(Pregnancy, on_delete=models.PROTECT, related_name="contacts")
    sequence = models.PositiveSmallIntegerField(default=0)
    place_type = models.CharField(max_length=50, blank=True)
    facility_name = models.CharField(max_length=200, blank=True)
    date = models.DateField(null=True, blank=True)
    onset_at = models.DateTimeField(null=True, blank=True)
    transport = models.CharField(max_length=100, blank=True)
    time_to_reach = models.PositiveIntegerField(null=True, blank=True)
    money_transport = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    attended_by = models.CharField(max_length=100, blank=True)
    reason_for_referral = models.TextField(blank=True)
    referral_slip = models.CharField(max_length=20, blank=True)
    treatment_given = models.TextField(blank=True)
    money_treatment = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    time_in_facility = models.PositiveIntegerField(null=True, blank=True)
    supersedes = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="superseded_by"
    )


class AdmissionDiagnosis(models.Model):
    admission = models.ForeignKey(Admission, on_delete=models.CASCADE, related_name="diagnoses")
    code = models.CharField(max_length=100)
    underlying_cause = models.CharField(max_length=200, blank=True)
    note = models.TextField(blank=True)


class Delivery(models.Model):
    pregnancy = models.ForeignKey(Pregnancy, on_delete=models.PROTECT, related_name="deliveries")
    delivered_at = models.DateTimeField(null=True, blank=True)
    time_precision = models.CharField(
        max_length=20, choices=TimePrecision.choices, default=TimePrecision.EXACT
    )
    mode = models.CharField(max_length=100, blank=True)
    facility = models.ForeignKey(Facility, on_delete=models.PROTECT, null=True, blank=True)
    performed_by = models.CharField(max_length=200, blank=True)
    supersedes = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="superseded_by"
    )
    note = models.TextField(blank=True)


class Neonate(models.Model):
    delivery = models.ForeignKey(Delivery, on_delete=models.PROTECT, related_name="neonates")
    outcome = models.CharField(max_length=100)
    assessed_at = models.DateTimeField(null=True, blank=True)
    status_context = models.CharField(max_length=100, blank=True)
    cause = models.CharField(max_length=200, blank=True)
    note = models.TextField(blank=True)


class IcuStay(models.Model):
    admission = models.ForeignKey(Admission, on_delete=models.PROTECT, related_name="icu_stays")
    from_at = models.DateTimeField(null=True, blank=True)
    from_precision = models.CharField(
        max_length=20, choices=TimePrecision.choices, default=TimePrecision.EXACT
    )
    to_at = models.DateTimeField(null=True, blank=True)
    to_precision = models.CharField(
        max_length=20, choices=TimePrecision.choices, default=TimePrecision.EXACT
    )
    note = models.TextField(blank=True)


class Transfusion(models.Model):
    admission = models.ForeignKey(Admission, on_delete=models.PROTECT, related_name="transfusions")
    at = models.DateTimeField(null=True, blank=True)
    component = models.CharField(max_length=50)
    units = models.PositiveSmallIntegerField(null=True, blank=True)
    reaction = models.CharField(max_length=200, blank=True)
    note = models.TextField(blank=True)


class Intervention(models.Model):
    admission = models.ForeignKey(Admission, on_delete=models.PROTECT, related_name="interventions")
    phase = models.CharField(max_length=50)
    kind = models.CharField(max_length=100)
    at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True)


class Death(models.Model):
    pregnancy = models.ForeignKey(Pregnancy, on_delete=models.PROTECT, related_name="deaths")
    admission = models.ForeignKey(
        Admission, on_delete=models.PROTECT, null=True, blank=True, related_name="deaths"
    )
    died_at = models.DateTimeField(null=True, blank=True)
    time_precision = models.CharField(
        max_length=20, choices=TimePrecision.choices, default=TimePrecision.EXACT
    )
    place = models.CharField(max_length=100, blank=True)
    brought_dead = models.BooleanField(default=False)
    certified_by = models.CharField(max_length=200, blank=True)
    supersedes = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="superseded_by"
    )


class Review(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        RETURNED = "returned", "Returned"
        APPROVED = "approved", "Approved"
        VOIDED = "voided", "Voided"

    pregnancy = models.ForeignKey(Pregnancy, on_delete=models.PROTECT, related_name="reviews")
    reporting_facility = models.ForeignKey(Facility, on_delete=models.PROTECT)
    reporting_admission = models.ForeignKey(
        Admission, on_delete=models.PROTECT, null=True, blank=True, related_name="reviews"
    )
    fbmdr_no = models.CharField(max_length=30, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    current_version = models.PositiveIntegerField(default=0)
    edit_revision = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="reviews_created",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="reviews_assigned",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="reviews_submitted",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    returned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="reviews_returned",
    )
    returned_at = models.DateTimeField(null=True, blank=True)
    return_comment = models.TextField(blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="reviews_approved",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    deadline_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"Review {self.pk} ({self.pregnancy.patient.name})"


class ReviewVersion(models.Model):
    class Kind(models.TextChoices):
        SUBMISSION = "submission", "Submission"
        APPROVAL = "approval", "Approval"
        AMENDMENT = "amendment", "Amendment"

    review = models.ForeignKey(Review, on_delete=models.PROTECT, related_name="versions")
    version_no = models.PositiveIntegerField()
    kind = models.CharField(max_length=20, choices=Kind.choices)
    payload_json = models.JSONField()
    payload_hash = models.CharField(max_length=64)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    amends_version = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="amended_by"
    )
    submission_version = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="approvals"
    )
    registry_version = models.CharField(max_length=20, default="r1")
    output_template_version = models.CharField(max_length=20, default="f4-2017@1")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["review", "version_no"], name="uniq_review_version_no")
        ]
        ordering = ["review", "version_no"]


class ReviewItem(models.Model):
    class AnswerState(models.TextChoices):
        UNANSWERED = "unanswered", "Unanswered"
        ANSWERED = "answered", "Answered"
        NOT_KNOWN = "not_known", "Not known"

    class Applicability(models.TextChoices):
        APPLICABLE = "applicable", "Applicable"
        NOT_APPLICABLE = "not_applicable", "Not applicable"
        UNDETERMINED = "undetermined", "Undetermined"

    class Origin(models.TextChoices):
        REUSED = "reused", "Reused"
        DERIVED = "derived", "Derived"
        ENTERED = "entered", "Entered"
        CORRECTED = "corrected", "Corrected"
        NONE = "none", "None"

    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name="items")
    field_key = models.CharField(max_length=120)
    answer_state = models.CharField(
        max_length=20, choices=AnswerState.choices, default=AnswerState.UNANSWERED
    )
    value_json = models.JSONField(null=True, blank=True)
    origin = models.CharField(max_length=20, choices=Origin.choices, default=Origin.NONE)
    reason = models.TextField(blank=True)
    applicability_state = models.CharField(
        max_length=20, choices=Applicability.choices, default=Applicability.APPLICABLE
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    accepted_proposal = models.ForeignKey(
        "Proposal", on_delete=models.SET_NULL, null=True, blank=True, related_name="accepted_by"
    )
    needs_reconsideration = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["review", "field_key"], name="uniq_review_field_key")
        ]


class Proposal(models.Model):
    class Status(models.TextChoices):
        PROPOSED = "proposed", "Proposed"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"
        SUPERSEDED = "superseded", "Superseded"
        STALE = "stale", "Stale"

    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name="proposals")
    field_key = models.CharField(max_length=120)
    rule_key = models.CharField(max_length=120)
    rule_version = models.PositiveSmallIntegerField(default=1)
    source_kind = models.CharField(max_length=50, default="observation")
    value_json = models.JSONField()
    frozen_inputs = models.JSONField(default=list, blank=True)
    input_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PROPOSED)
    status_reason = models.TextField(blank=True)

    class Meta:
        indexes = [models.Index(fields=["review", "field_key", "status"])]


class ProposalDecision(models.Model):
    proposal = models.ForeignKey(Proposal, on_delete=models.CASCADE, related_name="decisions")
    decision = models.CharField(max_length=20)
    by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    at = models.DateTimeField(auto_now_add=True)
    reason = models.TextField(blank=True)


class Amendment(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PROPOSED = "proposed", "Proposed"
        RETURNED = "returned", "Returned"
        APPROVED = "approved", "Approved"

    review = models.ForeignKey(Review, on_delete=models.PROTECT, related_name="amendments")
    base_version = models.ForeignKey(ReviewVersion, on_delete=models.PROTECT)
    payload_json = models.JSONField()
    reason = models.TextField()
    by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="amendments_decided",
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    return_comment = models.TextField(blank=True)


class AuditEvent(models.Model):
    at = models.DateTimeField(default=timezone.now)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True
    )
    action = models.CharField(max_length=50)
    entity_type = models.CharField(max_length=50)
    entity_id = models.CharField(max_length=50, blank=True)
    review = models.ForeignKey(
        Review, on_delete=models.PROTECT, null=True, blank=True, related_name="audit_events"
    )
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-at", "-id"]
