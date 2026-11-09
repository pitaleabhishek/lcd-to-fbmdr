# UI design


## What the app holds

The LCG is the only document that the app reads in. Admission, delivery, death and
neonatal events are facts. Staff record them in the app at the point of care. Each
fact has an author and a time. They are not documents that arrive later. This is
why a review can show values that the LCG does not contain. Those values are not a
second source.

## Principles

1. **Show status before detail.** The first view shows what is reused, what is
   missing and what does not apply. Detail is one tap away.
2. **Limit input. Do not warn after the fact.** If a value is not on the form, the
   user cannot enter it. Use a `select`, not a free text box and a later message.
3. **One main action per screen.** The workspace has Submit. The FNO screen has
   Approve or Return. No other action competes.
4. **Do not lose work.** Autosave. Show the state. Let the user resume.
5. **Show evidence beside the decision.** Show a proposal or alert next to the
   field. Include the source. Do not put it in a separate report.
6. **Show history on demand.** The user can open who changed what and when. The
   resident does not need to remember a separate tab.

## Standards

| Standard | What the app uses |
|---|---|
| WCAG 2.2 AA | Contrast, target size, focus, labels, error text, no colour-only meaning |
| GOV.UK and NHS.UK patterns | Task list, check your answers, error summary, one thing per page |
| IEC 62366-1 | Task analysis and error-prone scenarios |
| CDS five rights | Evidence at the point of decision, at the right time |
| Alert-fatigue guidance | Three tiers. No modal for clinical data |


## Message tiers

| Tier | Use | Example | Behaviour |
|---|---|---|---|
| Blocking | The form forbids it, or a required field is empty | `mode = "vaginal"` | Inline, red, stops submit |
| Warning | Valid but needs attention | The source changed after acceptance | Amber, does not stop submit |
| Info | Context for a judgement | “Systolic 150 at 22:30 crossed 140” | Grey, beside the field |

The app uses no modal for these tiers. A modal at 4 a.m. gets dismissed by reflex.

## Interaction

- Autosave on change. Show *saving*, *saved* or *error*. Keep a Save option.
- The header shows **last saved**, for example “saved 4 minutes ago”. A resident
  who was interrupted needs to know the work survived.
- Submit waits for saves in progress and sends `edit_revision`. A stale tab gets a
  recoverable message. It never overwrites without a warning.
- Keyboard first. Tab order follows the form. Enter saves. No traps.
- Touch targets are at least 44 px. Body text is at least 16 px. Use one column on
  a phone.
- No animation except a state change. Respect `prefers-reduced-motion`.

## Technology

- Django templates and server rendering. Actions use POST and redirect.
- HTMX for four tasks: autosave, provenance drawer, section counts and inline
  accept/reject. Nothing else.
- One small stylesheet. No Tailwind build, no component library and no SPA. Forms
  are the product.
- No charting. The app does not render the LCG chart. The assignment defers LCG
  charting.
