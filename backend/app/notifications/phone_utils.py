"""VisionGuard Phone Number Utilities (E.164 Canonicalization and Privacy Masking)."""

from __future__ import annotations

import re
from typing import Optional

# E.164 Regex: + followed by 1-3 digit country code and 7-14 digit subscriber number (total 8-15 digits)
E164_REGEX = re.compile(r"^\+[1-9]\d{7,14}$")


def normalize_phone_number(phone: str, default_country_code: Optional[str] = None) -> str:
    """Normalize phone number to international standard E.164.

    Strips whitespace, hyphens, dots, parentheses.
    Ensures '+' prefix and 8-15 total digits.
    Raises ValueError with descriptive reason if invalid.
    """
    if not phone or not isinstance(phone, str):
        raise ValueError("Invalid phone number: cannot be empty.")

    cleaned = re.sub(r"[\s\-\(\)\.]", "", phone.strip())
    if not cleaned.startswith("+"):
        if default_country_code:
            norm_cc = default_country_code.strip()
            if not norm_cc.startswith("+"):
                norm_cc = "+" + norm_cc
            cleaned = norm_cc + cleaned
        elif cleaned.isdigit() and len(cleaned) >= 11:
            # Assumed country code included without +
            cleaned = "+" + cleaned
        else:
            raise ValueError("Invalid phone number: must include international country code (e.g., +91 or +1).")

    if not E164_REGEX.match(cleaned):
        raise ValueError("Invalid phone number: format must adhere to E.164 (e.g., +919876543210).")

    return cleaned


def mask_phone_number(phone: str) -> str:
    """Mask phone number for safe display in UI/API responses without leaking full identity.

    Example: '+919876543210' -> '+91 ******3210'
    Example: '+15552345678' -> '+1 ******5678'
    """
    if not phone:
        return ""

    try:
        norm = normalize_phone_number(phone)
    except ValueError:
        if len(phone) > 4:
            return f"***{phone[-4:]}"
        return "****"

    if norm.startswith("+1") and len(norm) == 12:
        prefix = "+1"
    elif norm.startswith(("+91", "+44", "+33", "+49", "+61", "+81", "+86")):
        prefix = norm[:3]
    elif len(norm) > 11:
        prefix = norm[:3]
    else:
        prefix = norm[:2]

    suffix = norm[-4:]
    return f"{prefix} ******{suffix}"
