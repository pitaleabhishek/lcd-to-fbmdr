# UI design

The interface exists for one person: a resident at 4 a.m., post-call, on a phone,
who has just come out of a failed resuscitation and still has other patients. The
FNO uses the same screens in daylight, at a desk, deciding whether to approve.

Everything below follows from those two users.

## Principles

1. **Status before detail.** The first thing on screen is what is reused, what is
   missing, and what does not apply. Detail is one tap away.
2. **Constrain, don't warn.** If a value is not on the form, it cannot be entered.
   Validation is a `select`, not a message after the fact.
3. **One primary action per screen.** Submit on the workspace. Approve or return
   on the FNO screen. Nothing else competes.
4. **Never lose work.** Autosave, visible state, resumable after interruption.
5. **Evidence beside the decision.** A proposal or an alert is shown next to the
   field it affects, with its source, not in a separate report.
6. **History on demand.** Who changed what, when, is one expander away — not a tab
   the resident has to remember to open.

## Standards we follow

| Standard | What we take | What we don't |
|---|---|---|
| **WCAG 2.2 AA** | contrast, target size, focus, labels, error text, no colour-only meaning | formal audit or certification |
| **GOV.UK / NHS.UK patterns** | task list, check-your-answers, error summary, one thing per page | their visual style |
| **IEC 62366-1** | task analysis and error-prone scenarios written down | claiming device compliance |
| **CDS "five rights"** | evidence at the point of decision, at the right time | any automated clinical advice |
| **Alert-fatigue guidance** | three tiers, no modal for clinical data | alert tuning or ML |

We are **not** claiming clinical validation. That needs summative usability testing
with real clinicians, which is outside a seven-day build. It is stated here and in
the limitations note.

## Three message tiers

| Tier | Use | Example | Behaviour |
|---|---|---|---|
| **Blocking** | the form forbids it, or a required field is empty | `mode = "vaginal"` | inline, red, stops submit |
| **Warning** | valid but needs attention | source changed since this was accepted | amber, does not stop submit |
| **Info** | context for a judgement | "systolic 150 at 22:30 crossed ≥140" | grey, sits beside the field |

No modals for any of the three. A modal at 4 a.m. is dismissed reflexively.

## Error prevention, mapped to the data model

| Rule | Where it lives | UI effect |
|---|---|---|
| enum values come from the printed form | `form4_field.options` + trigger | a `select`, never a text box |
| block rows have fixed columns | `block_schema` | fixed table, no free-form rows |
| unknown field keys are rejected | trigger | impossible from the UI |
| N/A needs a reason | `ReviewItem.reason` | the N/A action asks for one |
| required fields gate submission | `missing_required()` | submit disabled, list of what is missing |
| no self-approval | service | approve hidden for the author |
| locked after approval | services + status | editing controls disappear |

## Screens

**Labour record** — read-only. Section 1 header, then sections 2–7 as rows of
variables against time columns. First/second stage banded. Missing observations are
visibly missing. A cell expands to author, observed / documented / entered times,
and a late-entry flag. This is "what he already filled".

**Review workspace** — the main screen.

- Header: patient, facility, status, `answered / total`, deadline, one primary action.
- Left: the 14 sections with counts and badges for *needs review* and *gap*.
- Rows: printed label, current answer with a source chip (`R` reused, `D` derived,
  `E` entered, `C` corrected), proposals with their inputs, accept / reject / edit,
  N/A with reason, required marker.
- Provenance drawer per row: source entry, times, author, rule and version.

**Submission check** — what is missing, what is not applicable, what still needs
reconsideration. Plain language, one line each, with a jump link.

**Output** — the printed Form 4 in sections, every value marked, provenance
appendix. Printable.

**Activity** — review history from `AuditEvent`: who accepted, rejected, corrected,
submitted, returned, approved, when.

## History and provenance

Two separate things:

- **Record history**: the labour timeline — who wrote what, when, and whether it
  was documented after death.
- **Review history**: per-field change log and the decision trail.

Provenance in the full sense — several documents for one pregnancy, supersession,
conflicting sources — is out of scope. What we show is the source entry, its time
and its author, which is what the brief asks for.

## Interaction rules

- Autosave on change; visible *saving / saved / error*; explicit Save fallback.
- Submit waits for in-flight saves and sends `edit_revision`; stale tabs get a
  recoverable message, never a silent overwrite.
- Keyboard-first: tab order follows the form, Enter saves, no traps.
- Touch targets ≥44 px; body text ≥16 px; one column on a phone.
- No animation beyond a state change; `prefers-reduced-motion` respected.

## Technology

- Django templates, server-rendered; POST/redirect for actions.
- HTMX for four things: autosave, provenance drawer, section counts, inline
  accept/reject. Nothing else.
- One small hand-written stylesheet. No Tailwind build, no component library, no
  SPA. Forms are the product.
- No charting. The LCG chart is deliberately not rendered; the assignment defers
  LCG charting.

## Deliberately not built

Dark mode, animations, dashboards, sparklines, a mobile app shell, custom fonts,
illustrations. None of them help a tired resident enter a value correctly, and each
one costs time that belongs to the blocks and the workflow.
