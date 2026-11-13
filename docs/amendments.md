# Amendments

An amendment is the only way to change an approved review. It keeps the author
and the reason. It becomes official only when an FNO approves it.

## Rules

- Only an approved review can change.
- A review can have one open amendment.
- The official Form 4 stays the same until approval.
- An amendment with no change cannot be submitted.
- Checks run on submit and again on approval.
- The person who submits cannot approve.
- A return and a source correction are not amendments.

## Roles

| Action | Resident | FNO |
|---|---|---|
| Open and edit an amendment | yes | no |
| Request an amendment | no | yes |
| Submit | yes | no |
| Return | no | yes |
| Approve | no | yes, unless they submitted it |

An FNO request creates a draft. The review author edits and submits the draft.

## Workflow

```
approved -> draft -> proposed -> approved
               ^         |
               +- returned
```

A returned amendment goes back for edit and submit. A user can discard a draft or
returned amendment.

## Checks and provenance

Submit freezes the amendment payload and the provenance for each field. Approval
checks both hashes. Unchanged fields keep the base provenance.

Conditions use the staged answers. The app does not run proposal rules again. The
author edits the approved values by hand.

If the labour record changes during an amendment, the app does not propose a new
value. The author must edit the value.

## Clinical amendment page

The author does not need the full workspace. `/review/<pk>/amend/<id>/quick/`
shows the same small clinical page as `/quick/`, on the staged amendment scope:

- the amendment reason and the number of changed fields;
- the clinical judgement fields and the contributing factors;
- the collapsed record sections, with changed values marked;
- **Submit amendment**, with the same one-step confirmation.

Opening `/quick/` on an approved review with an open amendment redirects the
author there. The review page banner also links straight to it with **Continue
clinical amendment**, next to **Full amendment record**. The FNO sees the page
read-only and only gets the full record link; the full amendment workspace stays
the audit view for provenance, history, checks and block fields.

## Limitations

- An amendment has one overall FNO return comment. It has no per-field comments.
- The app does not re-evaluate proposals during an amendment.
