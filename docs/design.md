# LCG to FBMDR: technical design

This prototype reuses labour documentation in Form 4. It keeps the source of each
value.

## Scope

**In scope:**

- LCG-shaped labour records.
- Death review with or without a labour record.
- Proposed reuse.
- Accept, reject and correct.
- Full Form 4.
- Checks, return and approval.
- Amendments.
- Structured output.

**Out of scope:**

- LCG charting.
- Government integrations.
- Death certificates.
- Committee module.
- Offline sync.
- AI narratives.
- Production deployment.
- FHIR.
- Multi-tenancy.

## Model

The app separates four things:

- **Facts** are what staff recorded: patient, admission, delivery, death and LCG.
- **ReviewItem** is what the clinician asserts for one Form 4 field.
- **Proposal** is a proposed value with frozen inputs and a rule version.
- **ReviewVersion** is the output that the app prints.

The app never edits recorded facts. A correction is a new row with `supersedes`.
The chain has no cycles or branches. All other data is editable. Each edit writes
an `AuditEvent`.

| Table | Purpose |
|---|---|
| `Facility`, `Patient`, `Pregnancy` | Identity and pregnancy |
| `Admission`, `Delivery`, `Neonate`, `Death` | Clinical facts |
| `SourceDocument`, `Observation` | LCG or other document and its entries |
| `IcuStay` | ICU duration |
| `Review` | One death review, status and links |
| `ReviewItem` | One answer for each Form 4 field, plus amendment staging |
| `Proposal`, `ProposalDecision` | Proposed reuse and the clinician decision |
| `ReviewVersion` | Frozen submission, approval or amendment payload |
| `Amendment` | One open attributed change to an approved review |
| `AuditEvent` | Who changed what and when |

The app does not read a Form 4 answer live from a domain table. It offers a
proposal. The clinician accepts, rejects or corrects it.

N/A has one state: `applicability_state`. The app does not use
`answer_state = not_applicable`.

## Fields and keys

- **Field**: one answer and one `ReviewItem`.
- **Block**: one repeating group. The app stores it as one `ReviewItem` with a row
  list.
- **Block field**: one cell. The key is `field_key#row_index`.

The key format is `f4.<section_key>.<slug>`. The app uses the section key, not the
printed number. Printed numbers repeat and split across sections.

The registry has 14 sections, 99 fields and 3 block schemas. The inventory comes
from the registry. All 99 labels match the printed form.

## Reuse

A rule returns a value and its inputs. It can also return a refusal: missing,
unknown or not applicable. A refusal does not fill a field. A proposed N/A needs
clinician confirmation.

Derived values show the calculation. Date-only and estimated values keep their
precision. The app does not add midnight or invent a duration. Cause of death,
diagnosis, factors and narrative are always clinician entries.

See `docs/overlap.md` for false friends and terminology differences.

## Validation and staleness

These cases block submission:

- Inconsistent typed values.
- Outcome contradicts a delivery.
- A required field is empty at submit.
- Reconsideration is unresolved.

A source change does not change an accepted or approved answer. The app marks an
editable answer as `needs_reconsideration`. An approved review changes only
through an amendment.

Checks run on submit and again on approval. Errors block. Warnings need explicit
confirmation.

## Workflow

```
draft -> submitted -> returned -> submitted -> approved
approved -> amendment draft -> proposed -> approved
```

The resident authors and submits. The FNO returns with a comment or approves. No
one can approve their own work. Approved reviews are locked. An amendment keeps a
private staged copy. It needs FNO approval. The previous version stays official
until approval.

## Output

Output comes from a `ReviewVersion`, not live tables. Each value shows `R`
(reused), `D` (derived), `E` (entered) or `C` (corrected). Each value has a frozen
provenance appendix with source, times, author, rule and decision.

The approved version has a clean printable Form 4 for wet signature. A pending
amendment output has a **DRAFT — NOT APPROVED** stamp. Old versions stay
reproducible.

Form 1 comes from the same review. It stays live and editable after Form 4
approval. Form 4 stays frozen.

## Security

The app applies these controls:

- Server-side object permissions on each view.
- CSRF on each state change.
- No state-changing GET.
- Secure cookies.
- A non-owner database role for append-only triggers.
- Small audit payloads.

The app uses fictional data. It does not claim DPDP compliance. Backups,
retention, consent and breach procedure remain gaps. See `docs/security.md`.
