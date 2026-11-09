"""Optional HTTP Basic auth in front of the whole app."""

from __future__ import annotations

import base64
import secrets

from django.conf import settings
from django.http import HttpResponse


class BasicAuthMiddleware:
    """Require one shared HTTP Basic login when the env vars are set."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(settings, "BASIC_AUTH_USER", "")
        password = getattr(settings, "BASIC_AUTH_PASSWORD", "")
        if not user and not password:
            return self.get_response(request)

        header = request.META.get("HTTP_AUTHORIZATION", "")
        if header.startswith("Basic "):
            try:
                raw = base64.b64decode(header[6:]).decode("utf-8")
                supplied_user, supplied_password = raw.split(":", 1)
            except (ValueError, UnicodeDecodeError):
                supplied_user = supplied_password = ""
            if secrets.compare_digest(supplied_user, user) and secrets.compare_digest(
                supplied_password, password
            ):
                return self.get_response(request)

        response = HttpResponse("Authentication required.", status=401)
        response["WWW-Authenticate"] = (
            f'Basic realm="{getattr(settings, "BASIC_AUTH_REALM", "LCD to FBMDR")}"'
        )
        return response
