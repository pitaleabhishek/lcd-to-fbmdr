# Integrity, confidentiality and DPDP

This prototype treats labour and death-review data as sensitive health
information.

It protects integrity in these ways:

- source facts are append-only.
- corrections use a new row.
- submitted versions are frozen.
- each value has a provenance snapshot.
- the app checks hashes at approval.
- the database role cannot rewrite recorded facts.

It protects confidentiality with authentication, object scoping, TLS and
encrypted backups.

The app does not claim full DPDP compliance. See `docs/security.md` for commands
and gaps.

## Data and roles

The data are:

- the deceased woman's identity, pregnancy, labour, delivery and death.
- staff identity and decisions.
- Form 4 answers, proposals, amendments, audit trail and provenance.

The hospital or health department is the **Data Fiduciary**. The operator is the
**Data Processor**.

## Integrity controls

- Source facts are append-only. A correction creates a new row with `supersedes`.
- Readers use the current correction, not the latest clock time.
- The app freezes submitted and approved payloads in `ReviewVersion`.
- Each printed value has a frozen provenance snapshot.
- The app checks payload and provenance hashes at approval and output.
- The app database role cannot rewrite append-only tables.
- Checks block missing, impossible and inconsistent submissions.
- Author and FNO roles are separate. No one can approve their own work.
- Each decision and amendment writes an `AuditEvent`.

## Confidentiality controls

- Each page requires login.
- Residents see their own or assigned reviews. FNOs see all reviews. Facility
  scoping is a gap.
- Labour and source records are scoped through an accessible pregnancy.
- Unauthorised access returns 404.
- Headers are hardened.
- Cookies are HTTP-only and `SameSite=Lax`.
- Caddy can add TLS. HSTS and secure cookies are on when `SECURE=1`.
- Postgres uses TLS 1.2 or later and SCRAM-SHA-256.
- The app uses a least-privilege database role.
- Backups use AES-256-CBC and PBKDF2.
- The app has no external analytics, AI or data sharing.

## DPDP status

| Area | Status |
|---|---|
| Purpose limit and minimisation | Partial. The registry follows Form 4. Review free-text fields. |
| Accuracy | Strong. Append-only facts, checks, frozen versions and provenance. |
| Security safeguards | Partial. TLS, scoping, least privilege and encrypted backups. No MFA or login throttling. |
| Notice | Not implemented. The deployment must add a privacy notice. |
| Consent and lawful basis | Not consent-based for a deceased patient. The deployment must document the lawful basis. |
| Breach notification | Not implemented. The deployment needs a runbook and Board notification. |
| Retention and erasure | Not implemented. The deployment needs a controlled purge policy. |
| Data-principal rights | Not implemented. The deployment needs access, correction, grievance and nominee processes. |
| Cross-border transfer | No transfer. Docker and Postgres run locally. |
| Research use | De-identify first. |

## Deceased patient

The Act does not clearly exclude deceased persons. Consent and rights use a living
person as the model. A maternal death review must use a documented lawful basis:

- State function.
- legal obligation.
- public health function.
- medical emergency.

The deployment also needs a process for a nominee or legal heir.

## Not claimed

The app does not claim DPDP certification or full compliance. It does not claim
clinical validation. It does not claim production MFA, full access logs,
scheduled off-host backups, breach tooling, a retention schedule or live-volume
encryption.
