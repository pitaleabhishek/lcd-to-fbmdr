"""Open a demo amendment on an already approved review.

The approved version is left untouched. The command stages a small, plausible
change and (unless ``--submit`` is given) leaves the amendment in draft so the
author can walk through editing, submitting and FNO approval in the demo.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from review import services
from review.models import Review


SAMPLE_REASON = (
    "Death review committee corrected the case summary after its meeting."
)
SAMPLE_TEXT = (
    "The committee reviewed the documented labour observations and the "
    "post-delivery course. The case summary has been updated after the meeting; "
    "the original approved version is unchanged."
)


class Command(BaseCommand):
    help = "Open a draft amendment on an approved review for the demo."

    def add_arguments(self, parser):
        parser.add_argument(
            "--review",
            type=int,
            help="Review id. Defaults to the most recently approved review.",
        )
        parser.add_argument(
            "--submit",
            action="store_true",
            help="Submit the amendment for FNO approval instead of leaving it draft.",
        )

    def handle(self, *args, **options):
        review = (
            Review.objects.filter(pk=options["review"]).first()
            if options.get("review")
            else Review.objects.filter(status=Review.Status.APPROVED)
            .order_by("-approved_at", "-pk")
            .first()
        )
        if review is None:
            raise CommandError(
                "No approved review found. Submit and approve a review first, "
                "or pass --review with an approved one."
            )
        if review.status != Review.Status.APPROVED:
            raise CommandError(
                f"Review {review.pk} is {review.get_status_display()}; "
                "only an approved review can be amended."
            )

        existing = services.open_amendment(review)
        if existing is not None:
            self.stdout.write(
                f"Review {review.pk} already has an open amendment "
                f"{existing.pk} ({existing.get_status_display()})."
            )
            self._print_urls(review, existing)
            return

        author = review.created_by or review.assigned_to
        if author is None:
            raise CommandError(f"Review {review.pk} has no author to open an amendment.")

        amendment = services.start_amendment(review, author, SAMPLE_REASON)
        services.set_answer(
            review,
            "f4.summary.text",
            SAMPLE_TEXT,
            author,
            "Corrected after the death review committee meeting",
            amendment=amendment,
        )
        if options.get("submit"):
            services.submit_amendment(amendment, author)
            amendment.refresh_from_db()
            self.stdout.write(
                self.style.SUCCESS(
                    f"amendment {amendment.pk} on review {review.pk} submitted for approval"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"draft amendment {amendment.pk} opened on review {review.pk}"
                )
            )
        self._print_urls(review, amendment)

    def _print_urls(self, review, amendment):
        self.stdout.write(f"Review:    /review/{review.pk}/")
        self.stdout.write(f"Amendment: /review/{review.pk}/amend/{amendment.pk}/")
        self.stdout.write(
            f"Draft out: /review/{review.pk}/amend/{amendment.pk}/output/"
        )
