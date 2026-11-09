# Security and DPDP notes

This is a prototype with fictional data. It has assignment-level controls. It does
not claim production compliance, DPDP compliance or clinical validation.

## Web security

- The app uses `SecurityMiddleware` and sends
  `X-Content-Type-Options: nosniff` and `Referrer-Policy: same-origin`.
- The clickjacking middleware sends `X-Frame-Options: DENY`.
- Session cookies are HTTP-only and `SameSite=Lax`.
- CSRF cookies are HTTP-only and `SameSite=Lax`.
- `SECURE=1` turns on HTTPS redirect, secure cookies and HSTS for one year. It
  also requires a real `SECRET_KEY`.
- `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` come from environment variables.
- Django password validators require at least 10 characters. They reject common
  passwords, numeric-only passwords and passwords similar to the user name. Seed
  passwords bypass the validators on purpose. New users do not bypass them.
- The app can add one shared HTTP Basic login before every page. Set both
  `BASIC_AUTH_USER` and `BASIC_AUTH_PASSWORD`. Use it only with HTTPS. It is a
  demo gate, not a user identity or MFA.

## Object scoping

- A resident can open only reviews that they created or are assigned.
- An FNO can open all reviews. Facility scoping is not implemented because there
  is no user-to-facility map yet.
- An unauthorised request returns **404**, not a redirect. This prevents ID
  enumeration.
- Labour records, history, corrections and source records are reachable only
  through a pregnancy that the user can access. A pregnancy with no review is
  visible so an author can start the first review.
- `new_review` hides pregnancies whose reviews the resident cannot access.
- `start_review` refuses a labour record when the user cannot access its existing
  review.

## Database roles

The app uses the owner connection by default. This keeps the demo working. A
least-privilege role is available:

```sh
python manage.py db_roles create --password mdr_app
python manage.py db_roles grant
```

Run the app with the new role:

```sh
DB_USER=mdr_app DB_PASSWORD=mdr_app python manage.py runserver
```

Docker Compose accepts the same settings:

```sh
DB_USER=mdr_app DB_PASSWORD=mdr_app docker compose up -d web
```

Migrations and `db_roles` still need the owner:

```sh
docker compose exec -e DB_USER=mdr -e DB_PASSWORD=mdr web \
  python manage.py migrate
docker compose exec -e DB_USER=mdr -e DB_PASSWORD=mdr web \
  python manage.py db_roles create --password mdr_app
```

The application role has these limits:

- It cannot create, alter or drop tables. It is `NOSUPERUSER NOCREATEDB
  NOCREATEROLE`.
- It cannot update or delete recorded facts. These tables are `SELECT` and
  `INSERT` only: `Observation`, `SourceDocument`, `Delivery`, `Death`, `AuditEvent`,
  `ProposalDecision` and `ReviewVersion`.
- It cannot write reference tables. LCG and Form 4 registries and permissions are
  `SELECT` only.
- It cannot delete reviews, patients, facilities, admissions, proposals,
  amendments, returns or other operational records. It can delete `ReviewItem`
  rows for amendment staging.
- It can read registries, write operational records, update review state, and
  update `auth_user.last_login` and sessions.

Migrations and the `post_migrate` registry sync need the owner connection:

```sh
DB_USER=mdr DB_PASSWORD=mdr python manage.py migrate
```

The app does not apply the role setup to an existing database volume. Run
`db_roles` after migrations on the database that you want to protect.

## Encryption in transit

**Browser to app:** the default `docker compose up` uses HTTP for the local demo.
A TLS profile adds Caddy with an internal CA:

```sh
SECURE=1 TRUST_PROXY=1 \
ALLOWED_HOSTS=localhost,127.0.0.1 \
CSRF_TRUSTED_ORIGINS=https://localhost:9443 \
SECRET_KEY='<a long random value>' \
docker compose --profile tls up -d --build
```

Open `https://localhost:9443`. Caddy ends TLS and proxies to `web:8000`. Django
sees `X-Forwarded-Proto: https` and sends HSTS, secure cookies and the other
headers.

The certificate uses Caddy's internal CA. The browser warns until you trust it:

```sh
docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt ./caddy-root.crt
# macOS:
sudo security add-trusted-cert -d -r trustRoot \
  -k /Library/Keychains/System.keychain caddy-root.crt
```

Do not commit `caddy-root.crt`. Use a public certificate for a real
deployment. Caddy can get one for a real host name.

Return to the plain HTTP demo:

```sh
docker compose --profile tls stop caddy
docker compose up -d web
```

`SECURE=1` needs a real `SECRET_KEY`. The app will not start with the dev key. The
compose web service passes `${SECRET_KEY:-dev-only-not-secret}`. Set the value in
the environment or in an untracked `.env` file.

**App to Postgres:** the database image makes a self-signed certificate on start
and uses `ssl=on`. The web service connects with `DB_SSLMODE=require`. The DB hop
is encrypted, but the app does not verify the certificate identity. For
production, use `sslmode=verify-full` and mount the CA. To use local Postgres
without TLS, set `DB_SSLMODE=prefer`.

## Encryption at rest

Docker does not encrypt its volumes. The live `pgdata` volume must sit on an
encrypted disk:

- macOS: FileVault or an encrypted APFS volume.
- Linux: LUKS or an encrypted block device.
- Cloud: an encrypted EBS or managed volume.

This is a host control. The repository cannot turn it on.

The repository does provide encrypted backups:

```sh
BACKUP_PASSPHRASE='a long passphrase' ./scripts/backup-db.sh
```

`pg_dump` goes into AES-256-CBC with PBKDF2. Plain text does not touch disk. Store
the passphrase away from the backup. Restore is destructive and guarded:

```sh
BACKUP_PASSPHRASE='...' RESTORE_CONFIRM=yes \
  ./scripts/restore-db.sh backups/mdr-YYYYMMDD-HHMMSS.dump.enc
```

Backups and `*.dump.enc` are gitignored. The passphrase is the only key. If you
lose it, you lose the backup.

## Postgres hardening

The `db` service does these things:

- uses `ssl=on`, TLS 1.2 minimum and a self-signed certificate.
- uses `password_encryption=scram-sha-256` and SCRAM host authentication.
- logs connections and disconnections.
- sets `idle_in_transaction_session_timeout=60000`.
- binds the host port to `127.0.0.1:55433`, not the public interface.
- keeps the memory limits and `max_connections=20`.

The `db_roles` application role is the real least-privilege control. The owner
connection is still the default so the demo and migrations keep working.

## DPDP status

| DPDP area | Project status |
|---|---|
| Notice and purpose (s.5, Rule 3) | Not implemented. The prototype has no privacy notice. |
| Consent (s.6) | Not implemented. The patient is deceased. The deployment needs a documented lawful basis, not consent. |
| Accuracy (s.8(3)) | Strong: append-only facts, corrections, provenance and frozen versions. |
| Security safeguards (s.8(5), Rule 6) | Web hardening, password validators, object scoping, TLS profile, Postgres TLS, SCRAM, connection logs, encrypted backups and an opt-in least-privilege role. Live-volume encryption is a host control. No MFA or login throttling. |
| Breach notification (s.8(6), Rule 7) | No incident workflow. |
| Retention and erasure (s.8(7), Rule 8) | No retention schedule or purge process. Append-only triggers block deletes. |
| Rights and grievance (ss.11-14, Rule 14) | No data-principal request or grievance workflow. Clinician correction exists. |
| Cross-border (s.16, Rule 15) | Local Docker and Postgres. No external transfer. |
| Children (s.9, Rules 10-12) | Neonatal outcome only. No child identifiers beyond the Form 4 field. The deployment must assess this. |

## Remaining work

- FNO facility scoping. This needs a user-to-facility map.
- Login throttling and MFA.
- Live-volume encryption, certificate identity checks (`verify-full`) and key
  management.
- Application access logs. Rule 6 asks for logs, monitoring and review. Domain
  audit and Postgres connection logs are not a full access log.
- Backup restore drills and off-host storage.
- Scheduled backups. The current script is manual.
- A breach runbook and a 72-hour Board notification template.
- A retention schedule and a controlled purge or anonymisation process. It must
  work with append-only facts and legal retention.
- A data-principal and nominee request process, plus a grievance process.
- A processor contract or DPA when hosting is outsourced.
- Legal review of the lawful basis for deceased-patient data.

The domain design is strong for accuracy and accountability. Some deployment
controls are in place. The list above shows the rest.
