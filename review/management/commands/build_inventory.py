"""Generate the overlap inventory from the registry and reconcile labels to the PDF text.

The inventory is an output, never a hand-maintained list.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from django.core.management.base import BaseCommand

from review.registry import CATEGORIES, registry
from review.rules import RULES

SOURCE = Path("docs/form4-source.txt")
CSV_OUT = Path("docs/inventory.csv")
MD_OUT = Path("docs/inventory.md")

RATIONALE = {
    "reused": "Recorded during labour and copied unchanged, with its source entry retained.",
    "derived": "Computed from recorded times; refusal states are preserved, never invented.",
    "none": "Not recorded during labour; the clinician enters it and owns the answer.",
}

STOP = {
    "the", "and", "with", "from", "time", "date", "type", "name", "form",
    "during", "after", "before", "other", "not", "yes", "unknown", "days",
}


def keywords(label: str) -> list[str]:
    return [w for w in re.findall(r"[a-z]{3,}", label.lower()) if w not in STOP]


def found(words: list[str], source: str) -> list[str]:
    return [w for w in words if re.search(rf"\b{re.escape(w)}\b", source)]


class Command(BaseCommand):
    help = "Write docs/inventory.csv and docs/inventory.md from the registry."

    def handle(self, *args, **options):
        source = SOURCE.read_text(encoding="utf-8").lower() if SOURCE.exists() else ""
        rows = []
        for f in registry.all():
            rule = RULES.get(f.key)
            relationship = rule.origin if rule else "none"
            kws = keywords(f.label_printed)
            matched = found(kws, source)
            rows.append(
                {
                    "key": f.key,
                    "section": f.section,
                    "category": f.category,
                    "category_name": CATEGORIES[f.category],
                    "label_printed": f.label_printed,
                    "type": f.type,
                    "handling": f.handling,
                    "relationship": relationship,
                    "source": f.source,
                    "rule": rule.key if rule else "",
                    "rationale": RATIONALE[relationship],
                    "terminology_note": f.terminology_note,
                    "precision_note": f.precision_note,
                    "pdf_matched": "yes" if matched else "no",
                    "pdf_terms": " ".join(matched),
                }
            )

        CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
        with CSV_OUT.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)

        by_rel: dict[str, int] = {}
        by_cat: dict[int, int] = {}
        by_src: dict[str, int] = {}
        for r in rows:
            by_rel[r["relationship"]] = by_rel.get(r["relationship"], 0) + 1
            by_cat[r["category"]] = by_cat.get(r["category"], 0) + 1
            by_src[r["source"]] = by_src.get(r["source"], 0) + 1

        lcg_n = by_src.get("lcg", 0)
        pct = (100.0 * lcg_n / len(rows)) if rows else 0.0
        md = ["# Form 4 overlap inventory", "",
              f"This file lists all {len(rows)} fields from the registry. "
              "The categories follow Dr Atter (4 November 2026). "
              "The app derives each relationship from the rules.", "",
              f"**Direct LCG reuse: {lcg_n} of {len(rows)} fields ({pct:.1f}%).** "
              "The clinician enters each other value, or the app copies it from "
              "another recorded fact.", ""]
        md.append("## By category")
        md.append("")
        md.append("| Category | Fields |")
        md.append("|---|---|")
        for c in sorted(by_cat):
            md.append(f"| {c}. {CATEGORIES[c]} | {by_cat[c]} |")
        md.append("")
        md.append("## By source of the value")
        md.append("")
        md.append("| Source | Fields |")
        md.append("|---|---|")
        for src, n in sorted(by_src.items(), key=lambda kv: -kv[1]):
            md.append(f"| {src} | {n} |")
        md.append("")
        md.append("## By relationship")
        md.append("")
        md.append("| Relationship | Fields |")
        md.append("|---|---|")
        for rel in ("reused", "derived", "none"):
            md.append(f"| {rel} | {by_rel.get(rel, 0)} |")
        md.append("")
        md.append("## Fields")
        md.append("")
        md.append("| Key | Category | Source | Printed item | Relationship | PDF label found |")
        md.append("|---|---|---|---|---|---|")
        for r in rows:
            md.append(
                f"| `{r['key']}` | {r['category']} | {r['source']} | {r['label_printed']} | "
                f"{r['relationship']} | {r['pdf_matched']} |"
            )
        MD_OUT.write_text("\n".join(md) + "\n", encoding="utf-8")

        unmatched = [r["key"] for r in rows if r["pdf_matched"] == "no"]
        self.stdout.write(
            f"{len(rows)} fields -> {CSV_OUT} and {MD_OUT}; "
            f"lcg-sourced {by_src.get('lcg', 0)}; "
            f"{len(unmatched)} labels not found in the PDF text"
        )
        for key in unmatched:
            self.stdout.write(f"  unmatched: {key}")
