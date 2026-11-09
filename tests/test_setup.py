from __future__ import annotations

from django.contrib.auth.models import User
from django.core.management import call_command

from review.models import Patient, Review


def test_demo_setup_seeds_the_cases(client, db):
    call_command("demo_setup", verbosity=0)

    names = set(Patient.objects.values_list("name", flat=True))
    assert {
        "Sunita Devi",
        "Anita K. Bhosale",
        "Lata S. Pawar",
        "Rekha S. Gawande",
        "Meena R. Deshmukh",
    } <= names
    review_names = {
        name
        for name in Review.objects.values_list(
            "pregnancy__patient__name", flat=True
        )
    }
    assert {
        "Sunita Devi",
        "Anita K. Bhosale",
        "Lata S. Pawar",
        "Rekha S. Gawande",
    } <= review_names
    assert User.objects.filter(username="resident").exists()
    assert User.objects.filter(username="fno").exists()

    client.force_login(User.objects.get(username="resident"))
    page = client.get("/").content.decode()
    for label in ("Case A", "Case B", "Case C", "Case D", "Happy case"):
        assert label in page


def test_demo_setup_is_idempotent(db):
    call_command("demo_setup", verbosity=0)
    patients = Patient.objects.count()
    reviews = Review.objects.count()

    call_command("demo_setup", verbosity=0)

    assert Patient.objects.count() == patients
    assert Review.objects.count() == reviews
