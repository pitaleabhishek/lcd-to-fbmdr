from __future__ import annotations

import base64

import pytest
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from review.models import Review


def test_basic_security_headers_are_sent(client):
    response = client.get("/login/")
    assert response.status_code == 200
    assert response["X-Frame-Options"] == "DENY"
    assert response["X-Content-Type-Options"] == "nosniff"
    assert response["Referrer-Policy"] == "same-origin"


@override_settings(BASIC_AUTH_USER="demo", BASIC_AUTH_PASSWORD="secret")
def test_basic_auth_blocks_without_credentials(client):
    response = client.get("/login/")
    assert response.status_code == 401
    assert response["WWW-Authenticate"].startswith("Basic ")


@override_settings(BASIC_AUTH_USER="demo", BASIC_AUTH_PASSWORD="secret")
def test_basic_auth_accepts_the_configured_user(client):
    token = base64.b64encode(b"demo:secret").decode("ascii")
    response = client.get("/login/", HTTP_AUTHORIZATION=f"Basic {token}")
    assert response.status_code == 200


@override_settings(BASIC_AUTH_USER="demo", BASIC_AUTH_PASSWORD="secret")
def test_basic_auth_rejects_the_wrong_password(client):
    token = base64.b64encode(b"demo:wrong").decode("ascii")
    response = client.get("/login/", HTTP_AUTHORIZATION=f"Basic {token}")
    assert response.status_code == 401


def test_basic_auth_is_off_when_unset(client):
    response = client.get("/login/")
    assert response.status_code == 200


def test_weak_passwords_are_rejected():
    with pytest.raises(ValidationError):
        validate_password("short")


def test_db_roles_status_requires_an_existing_role(db):
    with pytest.raises(CommandError):
        call_command("db_roles", "status", role="no_such_role_for_the_test")


@pytest.mark.django_db
def test_review_scoping_is_applied_to_the_index(client):
    call_command("seed_case_a", verbosity=0)
    review = Review.objects.get()
    other = User.objects.create_user(username="other_resident", password="otherpass123")
    client.force_login(other)
    page = client.get("/").content.decode()
    assert review.pregnancy.patient.name not in page

    fno = User.objects.get(username="fno")
    client.force_login(fno)
    page = client.get("/").content.decode()
    assert review.pregnancy.patient.name in page
