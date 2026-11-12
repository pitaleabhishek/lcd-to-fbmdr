# LCG to FBMDR

This app reuses labour data from the WHO Labour Care Guide (LCG) in a
Facility-Based Maternal Death Review (Form 4). Each value keeps its source. The
user does not type the same data again.

Hosted demo: `https://lcgtofbmdr.nirovia.in`

The hosted demo has two gates:

1. HTTP Basic auth. Use the deployment credentials.
2. App login:

| User | Password | Role |
|---|---|---|
| `resident` | `resident123` | author |
| `fno` | `fno123` | approver |

## Demo walkthrough: approve, amend, approve again

Use the **Happy case**: patient **Meena R. Deshmukh**. Open the review by patient
name. The review ID can change after a reset.

### 1. Log in as the resident

Open the app and log in:

```text
resident / resident123
```

### 2. Open the Happy case

Open the review for **Meena R. Deshmukh**. The resident lands on **Clinical
review**, not the full 99-field form.

This case is a clean LCG and a complete draft:

- 100% resolved
- no required gaps
- no check issues
- source values, derived values and entered values all present

### 3. Review the short form

The page shows:

- a read-only **From the record** summary
- clinical fields: diagnosis, cause of death, autopsy, summary and sign-off
- a collapsible contributing-factors checklist
- only the conditional fields that apply, such as autopsy diagnosis or neonatal cause
- a **Full Form 4** link for the complete 99-field record

There is no history or provenance on this page. Those stay in the full record.

### 4. Submit

Add a note for the FNO, for example:

```text
Times checked against the labour record. Ready for review.
```

Click **Submit review**.

Checks run at submit. This case is clean, so it submits directly.

The review status changes to **Submitted**. A frozen version is created.

For the full 99-field record, click **Full Form 4**.

### 5. Return it as the FNO

Sign out and log in:

```text
fno / fno123
```

Open the same review. The FNO uses the full form.

Add one field comment. For example, open the comment box on **10. Case summary**
and write:

```text
Add one sentence about the baby's condition at birth.
```

Add an overall comment, then click **Return**.

The review status changes to **Returned**.

### 6. Fix it as the resident

Sign out and log in as `resident`.

Open the review. The return comment appears on the Clinical review page, and
the field comment is shown beside the relevant question.

Edit the case summary and add the missing sentence.

Click **Submit review** again.

### 7. Approve it as the FNO

Sign out and log in as `fno`.

Open the review and click **Approve**.

The review status changes to **Approved**. Form 4 is now locked.

Open **Approved version** to see the frozen output and provenance appendix.

### 8. Start an amendment

Log in as `resident`.

Open the approved review. Click **Propose amendment**.

Enter a reason, for example:

```text
Committee correction: clarify the summary.
```

Click **Create draft amendment**.

Edit the case summary. The changed field is highlighted and shows the approved
value and the draft value.

Click **Submit amendment for approval**.

### 9. Approve the amendment

Log in as `fno`.

Open the amendment and click **Approve amendment**.

This creates a new approved version. The previous version stays in history. The
output now shows the amendment and its reason.

## What this walkthrough demonstrates

- conditional Form 4
- evidence and provenance beside each value
- pre-submission checks
- submit, return with comments, fix and resubmit
- approval and lock
- amendment with a reason
- second approval and version history

## Run locally

You need Docker. Then run one command:

```sh
./start.sh
```

Windows PowerShell:

```powershell
.\start.ps1
```

The script starts Postgres, builds the app, runs migrations, seeds the demo cases
and opens `http://127.0.0.1:8000`.

Local setup has no Basic auth by default. To add it:

```sh
BASIC_AUTH_USER=demo BASIC_AUTH_PASSWORD='a long password' ./start.sh
```

See [`docs/setup.md`](docs/setup.md).

## The four required cases

The assignment needs four synthetic cases. All four are seeded.

| Case | Patient | What it is for | Checks and conditions it exercises |
|---|---|---|---|
| A | **Sunita Devi** | Death after a charted labour. The LCG has a gap and a late entry. | Source reuse, derived intervals, late-entry warning, missing required answers, live-birth branch, delivery and postnatal fields |
| B | **Anita K. Bhosale** | Caesarean after a first stage of charted labour. | First-stage caesarean, no second-stage observations, late-entry warning, mode and indication, delivery branch |
| C | **Lata S. Pawar** | Death with no labour record, before delivery. | No-labour warning, undelivered branch, hidden delivery/neonatal/postnatal fields, N/A on non-applicable fields |
| D | **Rekha S. Gawande** | Delivered at a PHC, referred in, then died. | Delivery-before-admission warning, `1.e` N/A, no-labour warning, referral table, parent N/A hides children, complete draft |

All four required cases have draft reviews in a fresh demo database. Cases B and
C start as blank drafts with proposals. Cases A and D also start as drafts.

In the hosted demo:

- **Case B** is fully filled and shows the late-entry warning.
- **Case D** is fully filled and shows the delivery-before-admission and
  no-labour-record warnings.
- **Happy case** is fully filled with no checks.
- **Cases A and C** remain proposal drafts.

The review index labels rows as **Case A** to **Case D**, and **Happy case**.

There is one extra fixture:

| Fixture | Patient | Purpose |
|---|---|---|
| Happy case | **Meena R. Deshmukh** | Clean LCG and complete draft. Used for the full approve/amend demo |

The `seed_case_0` command still exists for LCG chart tests. It is not part of the
demo setup.

## Checks and conditions: what is implemented

Checks run only on **Check before submitting** or **Submit**. Errors block.
Warnings need one **Submit anyway** confirmation.

Checks cover:

- missing required fields, follow-ups and specification fields
- impossible dates, negative values, zero units and exclusive answers
- inconsistent outcome, delivery, neonatal and postnatal answers
- admission, delivery and death order
- date-only, estimated and late entries
- interval, ICU and transfusion consistency
- retained answers in hidden questions
- source corrections and multiple current records
- no labour record and empty case summary

Conditions cover:

- abortion section only when the outcome is abortion
- delivery section only for live birth, still birth, undelivered or ectopic
- ANC follow-ups for facility, provider, counselling and risk factors
- referral places and referral table
- delivery, anaesthesia, partograph, complication and neonatal branches
- post-birth interval only when phase is `post_birth`
- neonatal cause only when the baby died
- parent N/A hides child fields
- hidden answers are kept but not printed
- FNO comments force a hidden field back into view

Full rules:

- [`docs/checks.md`](docs/checks.md)
- [`docs/conditions.md`](docs/conditions.md)

## Reference PDFs

The source documents are in [`docs/reference/`](docs/reference/):

- [Digitising Maternal Death Review](docs/reference/Digitising%20Maternal%20Death%20Review.pdf)
- [Digitising Maternal Death Review: answered](docs/reference/Digitising%20Maternal%20Death%20Review_answered.pdf)
- [IPHS](docs/reference/IPHS.pdf)
- [MDSR](docs/reference/MDSR.pdf)
- [WHO LCG](docs/reference/WHO%20LCG.pdf)
- [WHO Labour Care Guide form](docs/reference/who-labour-care-guide%20form.pdf)

## Project documents

- Setup: [`docs/setup.md`](docs/setup.md)
- Design: [`docs/design.md`](docs/design.md)
- Database audit: [`docs/db-audit.md`](docs/db-audit.md)
- Amendments: [`docs/amendments.md`](docs/amendments.md)
- Form 1: [`docs/form1.md`](docs/form1.md)
- LCG storage: [`docs/lcg-storage.md`](docs/lcg-storage.md)
- Overlap analysis: [`docs/overlap.md`](docs/overlap.md)
- Security: [`docs/security.md`](docs/security.md)
- DPDP: [`docs/dpdp.md`](docs/dpdp.md)
- Dependencies: [`docs/dependencies.md`](docs/dependencies.md)
- Evidence map: [`docs/evidence-map.md`](docs/evidence-map.md)
- UI rules: [`docs/ui.md`](docs/ui.md)
- Agent handoff: [`AGENTS.md`](AGENTS.md)
- Task list: [`TODO.md`](TODO.md)

## Tests

```sh
uv run pytest
uv run pytest -n 0     # one process for debugging
```

The suite has **264 passing tests**.

## Current state

- Form 4: 14 sections, 99 fields, 3 block schemas.
- LCG: 7 sections, 34 variables, Postgres-validated observations.
- All four required synthetic cases are seeded.
- Proposals, provenance and derived values.
- Accept, reject and correct.
- Conditional Form 4.
- Pre-submission checks.
- Quick clinical review: judgement and sign-off fields, a contributing-factors checklist, conditional fields and exceptions. No history or provenance on the clinician page.
- Submit, return, resubmit and approve.
- Amendments with a second approval.
- Form 1 from the same review.
- Printable Form 4 and frozen HTML/JSON output.
- One-command local setup.
- Optional HTTP Basic auth for the hosted demo.

Not complete: FNO facility scoping, MFA and login throttling, full access logs,
live-volume encryption, `verify-full` certificate checks, scheduled off-host
backups, breach tooling, retention and the demo script.
