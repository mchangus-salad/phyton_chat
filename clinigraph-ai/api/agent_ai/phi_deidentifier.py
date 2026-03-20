"""
HIPAA Safe Harbor De-identification  (45 CFR §164.514(b))

Redacts all 18 categories of Protected Health Information (PHI) from
free-text clinical documents before any LLM processing.

WARNING: This module provides best-effort automated de-identification.
Clinical documents that may be disclosed externally should also undergo
qualified human review.  This tool is NOT a substitute for a formal
HIPAA compliance programme.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class RedactionSummary:
    """Audit record of what categories were redacted.  Never contains the original PHI."""

    total_redactions: int = 0
    categories: dict[str, int] = field(default_factory=dict)

    def add(self, category: str) -> None:
        self.total_redactions += 1
        self.categories[category] = self.categories.get(category, 0) + 1

    def as_dict(self) -> dict:
        return {
            "total_redactions": self.total_redactions,
            "categories": dict(self.categories),
        }


# ── Pattern registry ─────────────────────────────────────────────────────────
# Tuples: (category_label, compiled_regex, replacement_token)
# Applied in order — more specific patterns are listed first so earlier
# replacements immunise already-redacted tokens against later patterns.

_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    # ── 1. Social Security Numbers ──────────────────────────────────────────
    (
        "SSN",
        re.compile(r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b"),
        "[SSN REDACTED]",
    ),
    # ── 2. Email addresses ──────────────────────────────────────────────────
    (
        "EMAIL",
        re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
        "[EMAIL REDACTED]",
    ),
    # ── 3. URLs / web addresses ─────────────────────────────────────────────
    (
        "URL",
        re.compile(r"\bhttps?://[^\s<>\"']+", re.IGNORECASE),
        "[URL REDACTED]",
    ),
    # ── 4. IPv4 addresses ───────────────────────────────────────────────────
    (
        "IP_ADDRESS",
        re.compile(
            r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}"
            r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
        ),
        "[IP REDACTED]",
    ),
    # ── 5. US Phone / Fax numbers ───────────────────────────────────────────
    (
        "PHONE_FAX",
        re.compile(
            r"\b(?:\+?1[-.\s]?)?"
            r"(?:\(\d{3}\)|\d{3})"
            r"[-.\s]?\d{3}[-.\s]?\d{4}\b"
        ),
        "[PHONE REDACTED]",
    ),
    # ── 6. Fax numbers explicitly labeled ───────────────────────────────────
    (
        "FAX",
        re.compile(
            r"\bfax[\s:]*(?:\+?1[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]?\d{3}[-.\s]?\d{4}\b",
            re.IGNORECASE,
        ),
        "[FAX REDACTED]",
    ),
    # ── 7. Medical Record Numbers ───────────────────────────────────────────
    (
        "MRN",
        re.compile(
            r"\b(?:MRN|M\.?R\.?N\.?|"
            r"medical\s+record\s+(?:number|#|no\.?|num\.?))"
            r"[\s:#]*[A-Za-z0-9\-]{3,15}\b",
            re.IGNORECASE,
        ),
        "[MRN REDACTED]",
    ),
    # ── 8. NPI / DEA / license / certificate numbers ────────────────────────
    (
        "LICENSE",
        re.compile(
            r"\b(?:NPI|DEA|license|licence|cert(?:ificate)?)"
            r"[\s.:#]*[A-Za-z0-9\-]{5,15}\b",
            re.IGNORECASE,
        ),
        "[LICENSE REDACTED]",
    ),
    # ── 9. Health plan / account / beneficiary / member numbers ─────────────
    (
        "ACCOUNT_NUMBER",
        re.compile(
            r"\b(?:account|acct|health\s+plan|beneficiary|"
            r"member\s+(?:id|number)|policy\s+(?:number|#|no\.?))"
            r"[\s.:#]*[A-Za-z0-9\-]{5,20}\b",
            re.IGNORECASE,
        ),
        "[ACCOUNT REDACTED]",
    ),
    # ── 10. Vehicle Identification Numbers (VIN, ISO 3779) ──────────────────
    (
        "VIN",
        re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b"),
        "[VIN REDACTED]",
    ),
    # ── 11. Device serial numbers ───────────────────────────────────────────
    (
        "DEVICE_SERIAL",
        re.compile(
            r"\b(?:serial(?:\s+(?:number|#|no\.?))?|S/N|SN)"
            r"[\s:#]*[A-Za-z0-9\-]{4,20}\b",
            re.IGNORECASE,
        ),
        "[DEVICE-ID REDACTED]",
    ),
    # ── 12. Ages > 89 (HIPAA requirement) ───────────────────────────────────
    (
        "AGE_OVER_89",
        re.compile(
            r"\b(?:9\d|1[01]\d|120)\s*[-\u2013]?\s*"
            r"(?:year|yr)s?(?:\s*[-\u2013]?\s*old)?\b",
            re.IGNORECASE,
        ),
        "[AGE REDACTED]",
    ),
    # ── 13. Explicit dates (all common formats except year-only) ────────────
    (
        "DATE",
        re.compile(
            r"\b(?:"
            # "January 15, 2024"  /  "Jan 15 2024"
            r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
            r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
            r"[\s,]+\d{1,2}(?:st|nd|rd|th)?[,\s]+\d{4}"
            # "15 January 2024"
            r"|\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
            r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
            r"\s+\d{4}"
            # MM/DD/YYYY  MM-DD-YYYY  MM.DD.YYYY
            r"|\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}"
            # YYYY-MM-DD  YYYY/MM/DD
            r"|\d{4}[/\-]\d{1,2}[/\-]\d{1,2}"
            r")\b",
            re.IGNORECASE,
        ),
        "[DATE REDACTED]",
    ),
    # ── 14. US Street addresses ──────────────────────────────────────────────
    (
        "STREET_ADDRESS",
        re.compile(
            r"\b\d+\s+(?:[A-Za-z]+\s){1,4}"
            r"(?:Street|St|Avenue|Ave|Boulevard|Blvd|Drive|Dr|Road|Rd|"
            r"Lane|Ln|Way|Parkway|Pkwy|Plaza|Court|Ct|Circle|Cir|"
            r"Terrace|Ter|Trail|Trl|Highway|Hwy|Route|Rte)\b",
            re.IGNORECASE,
        ),
        "[ADDRESS REDACTED]",
    ),
    # ── 15. US ZIP codes (labeled or in "City, ST 12345" format) ────────────
    (
        "ZIP_CODE",
        re.compile(
            r"(?:"
            r"\bzip(?:\s+code)?[\s.:]*\d{5}(?:-\d{4})?\b"        # "zip 90210"
            r"|,\s*[A-Z]{2}\s+\d{5}(?:-\d{4})?\b"                # ", CA 90210"
            r")",
            re.IGNORECASE,
        ),
        "[ZIP REDACTED]",
    ),
    # ── 16. Patient name when explicitly labeled ─────────────────────────────
    (
        "PATIENT_NAME",
        re.compile(
            r"(?:patient(?:\s+name)?|pt\.?|name)\s*[:=]\s*"
            r"([A-Z][a-z]{1,25}(?:\s+[A-Z][a-z]{1,25}){1,3})",
            re.IGNORECASE,
        ),
        "[PATIENT-NAME REDACTED]",
    ),
    # ── 17. Provider names when titled (Dr., NP, PA, MD, DO …) ─────────────
    (
        "PROVIDER_NAME",
        re.compile(
            r"\b(?:Dr\.?|Doctor|Physician|Attending|Resident|"
            r"Nurse\s+Practitioner|NP|PA|MD|DO)\s*\.?\s+"
            r"[A-Z][a-z]{1,25}(?:\s+[A-Z][a-z]{1,25})?\b",
        ),
        "[PROVIDER REDACTED]",
    ),
    # ── 18. Hospital / clinic facility names ────────────────────────────────
    #        Matched only when followed by an unambiguous org suffix to
    #        avoid false positives on generic medical terminology.
    (
        "FACILITY_NAME",
        re.compile(
            r"\b(?:[A-Z][a-z]+\s+){1,5}"
            r"(?:Hospital|Medical\s+Center|Medical\s+Centre|Health\s+System|"
            r"Healthcare\s+System|Surgery\s+Center|Cancer\s+Center)\b",
        ),
        "[FACILITY REDACTED]",
    ),
]


def deidentify(text: str) -> tuple[str, RedactionSummary]:
    """
    Apply HIPAA Safe Harbor de-identification to clinical free-text.

    Args:
        text: Raw clinical text that may contain PHI.

    Returns:
        (de_identified_text, RedactionSummary)

    Each pattern is applied once in order.  Replacement tokens like
    ``[SSN REDACTED]`` are plain ASCII and will not be re-matched by
    later patterns, preventing double-substitution.
    """
    summary = RedactionSummary()
    result = text

    for category, pattern, replacement in _PATTERNS:
        def _replace(m: re.Match, cat: str = category, repl: str = replacement) -> str:
            summary.add(cat)
            return repl

        result = pattern.sub(_replace, result)

    return result, summary
