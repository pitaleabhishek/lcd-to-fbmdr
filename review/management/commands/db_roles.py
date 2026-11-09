"""Create and grant a least-privilege Postgres role for the running app.

The role is deliberately not the table owner and cannot run DDL. Append-only
tables get SELECT/INSERT only, so the app cannot rewrite a recorded fact even if
a view is compromised. Migrations and seeds stay with the owner role.

Usage:

    python manage.py db_roles create --password ...
    python manage.py db_roles grant
    DB_USER=mdr_app DB_PASSWORD=... python manage.py runserver

This command itself must run as the owner (the role that created the tables).
"""

from __future__ import annotations

import os

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from psycopg import sql

DEFAULT_ROLE = "mdr_app"

# Immutable facts: corrections are new rows, never updates or deletes.
APPEND_ONLY = (
    "review_observation",
    "review_sourcedocument",
    "review_delivery",
    "review_death",
    "review_auditevent",
    "review_proposaldecision",
    "review_reviewversion",
)

# Reference tables are written by migrations/post_migrate, not the app.
REFERENCE = (
    "review_lcgsection",
    "review_lcgvariable",
    "review_form4section",
    "review_form4field",
    "auth_permission",
    "django_content_type",
    "django_migrations",
)

# Operational records the app creates and reads, but never deletes.
NO_DELETE = (
    "review_facility",
    "review_patient",
    "review_pregnancy",
    "review_admission",
    "review_neonate",
    "review_icustay",
    "review_review",
    "review_reviewreturn",
    "review_proposal",
    "review_amendment",
    "review_form1",
)


class Command(BaseCommand):
    help = "Create and grant the least-privilege application database role."

    def add_arguments(self, parser):
        parser.add_argument("action", choices=("create", "grant", "status"))
        parser.add_argument("--role", default=DEFAULT_ROLE)
        parser.add_argument(
            "--password",
            default=os.environ.get("DB_APP_PASSWORD", "mdr_app"),
            help="Password for the application role (default: DB_APP_PASSWORD).",
        )

    def handle(self, *args, **options):
        action = options["action"]
        role = options["role"]
        if action == "create":
            self._create(role, options["password"])
        elif action == "grant":
            self._grant(role)
        else:
            self._status(role)

    def _exists(self, cur, role: str) -> bool:
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [role])
        return cur.fetchone() is not None

    def _create(self, role: str, password: str):
        with connection.cursor() as cur:
            if self._exists(cur, role):
                cur.execute(
                    sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(
                        sql.Identifier(role), sql.Literal(password)
                    )
                )
                self.stdout.write(f"updated role {role}")
            else:
                cur.execute(
                    sql.SQL(
                        "CREATE ROLE {} WITH LOGIN PASSWORD {} "
                        "NOSUPERUSER NOCREATEDB NOCREATEROLE"
                    ).format(sql.Identifier(role), sql.Literal(password))
                )
                self.stdout.write(self.style.SUCCESS(f"created role {role}"))
            cur.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                    sql.Identifier(connection.settings_dict["NAME"]),
                    sql.Identifier(role),
                )
            )
            cur.execute(
                sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(
                    sql.Identifier(role)
                )
            )
        self.stdout.write(
            "Next: python manage.py db_roles grant, then set DB_USER/DB_PASSWORD."
        )

    def _grant(self, role: str):
        with connection.cursor() as cur:
            if not self._exists(cur, role):
                raise CommandError(
                    f"role {role} does not exist; run db_roles create first"
                )
            cur.execute(
                sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(
                    sql.Identifier(role)
                )
            )
            cur.execute(
                sql.SQL("REVOKE CREATE ON SCHEMA public FROM {}").format(
                    sql.Identifier(role)
                )
            )
            cur.execute(
                sql.SQL(
                    "GRANT SELECT, INSERT, UPDATE, DELETE "
                    "ON ALL TABLES IN SCHEMA public TO {}"
                ).format(sql.Identifier(role))
            )
            cur.execute(
                sql.SQL(
                    "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}"
                ).format(sql.Identifier(role))
            )
            cur.execute(
                sql.SQL(
                    "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                    "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}"
                ).format(sql.Identifier(role))
            )
            cur.execute(
                sql.SQL(
                    "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                    "GRANT USAGE, SELECT ON SEQUENCES TO {}"
                ).format(sql.Identifier(role))
            )

            for table in APPEND_ONLY:
                cur.execute(
                    sql.SQL("REVOKE UPDATE, DELETE ON TABLE {} FROM {}").format(
                        sql.Identifier(table), sql.Identifier(role)
                    )
                )
            for table in REFERENCE:
                cur.execute(
                    sql.SQL(
                        "REVOKE INSERT, UPDATE, DELETE ON TABLE {} FROM {}"
                    ).format(sql.Identifier(table), sql.Identifier(role))
                )
            for table in NO_DELETE:
                cur.execute(
                    sql.SQL("REVOKE DELETE ON TABLE {} FROM {}").format(
                        sql.Identifier(table), sql.Identifier(role)
                    )
                )
            # last_login is updated on every login.
            cur.execute(
                sql.SQL("REVOKE DELETE ON TABLE auth_user FROM {}").format(
                    sql.Identifier(role)
                )
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"granted least privilege to {role}: "
                "no DDL, append-only tables are SELECT/INSERT only"
            )
        )

    def _status(self, role: str):
        with connection.cursor() as cur:
            if not self._exists(cur, role):
                raise CommandError(f"role {role} does not exist")
            cur.execute(
                "SELECT rolname, rolsuper, rolcreatedb, rolcreaterole "
                "FROM pg_roles WHERE rolname = %s",
                [role],
            )
            row = cur.fetchone()
            self.stdout.write(
                f"{row[0]}: superuser={row[1]} createdb={row[2]} createrole={row[3]}"
            )
            cur.execute(
                "SELECT table_name, privilege_type "
                "FROM information_schema.table_privileges "
                "WHERE grantee = %s AND table_schema = 'public' "
                "ORDER BY table_name, privilege_type",
                [role],
            )
            for table, privilege in cur.fetchall():
                self.stdout.write(f"  {table}: {privilege}")
