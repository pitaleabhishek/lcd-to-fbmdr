from __future__ import annotations

from django.contrib.auth.models import User
from django.core.management import call_command

from review import checks, services
from review.models import Review


def test_seeded_happy_case_has_no_check_issues(db):
    call_command("seed_happy_case", verbosity=0)
    review = Review.objects.get(pregnancy__patient__name="Meena R. Deshmukh")

    assert checks.run_checks(review) == []
    assert review.items.count() == 83  # 79 applicable answers + 4 abortion N/A rows
    assert review.proposals.filter(status="proposed").count() == 0


def test_icu_and_review_source_links_resolve(client, db):
    call_command("seed_happy_case", verbosity=0)
    review = Review.objects.get(pregnancy__patient__name="Meena R. Deshmukh")
    icu = review.reporting_admission.icu_stays.first()
    client.force_login(User.objects.get(username="resident"))

    assert client.get(f"/source/icu/{icu.pk}/").status_code == 200
    assert client.get(f"/source/review/{review.pk}/").status_code == 200


def test_seeded_happy_case_submits_and_approves(db):
    call_command("seed_happy_case", verbosity=0)
    review = Review.objects.get(pregnancy__patient__name="Meena R. Deshmukh")
    resident = User.objects.get(username="resident")
    fno = User.objects.get(username="fno")

    version = services.submit(review, resident)
    assert version.version_no == 1
    services.approve(review, fno)
    review.refresh_from_db()
    assert review.status == Review.Status.APPROVED
    assert review.current_version == 2
