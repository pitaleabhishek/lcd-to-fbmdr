# Database audit

The database has **32 tables** after the cleanup.

- 9 are Django framework tables.
- 23 are review tables.

## Removed

| Table | Reason |
|---|---|
| `review_carecontact` | No code use. The referral table is stored in `ReviewItem`. |
| `review_transfusion` | No code use. Transfusion is stored in `ReviewItem`. |
| `review_intervention` | No code use. The intervention matrix is stored in `ReviewItem`. |
| `review_admissiondiagnosis` | Only `seed_case_d` wrote it. Nothing read it. |

Migration: `0025_remove_carecontact_pregnancy_and_more.py`.

## Kept

Framework tables:

- `auth_group`, `auth_group_permissions`, `auth_permission`, `auth_user`
- `auth_user_groups`, `auth_user_user_permissions`
- `django_content_type`, `django_migrations`, `django_session`

Empty auth join tables are part of Django auth. They are not dead tables.

Review tables:

- Identity and facts: `review_facility`, `review_patient`, `review_pregnancy`,
  `review_admission`, `review_delivery`, `review_neonate`, `review_death`
- LCG: `review_lcgsection`, `review_lcgvariable`, `review_sourcedocument`,
  `review_observation`
- Form 4 registry: `review_form4section`, `review_form4field`
- Review work: `review_review`, `review_reviewitem`, `review_reviewversion`,
  `review_proposal`, `review_proposaldecision`, `review_amendment`,
  `review_reviewreturn`, `review_form1`, `review_auditevent`
- ICU duration: `review_icustay`

Do not drop framework tables with raw SQL. Use Django migrations for any model
removal.
