"""
transforms.py
-------------
Normalization functions applied to a value BEFORE comparing source vs
destination. Use these to encode "expected" transformations (e.g. phone
reformatting, case normalization) so they don't get flagged as mismatches.

Add your own by writing a function(value) -> value and registering it
in TRANSFORMS below, then reference its name in config.json.
"""

import re


def none(v):
    return v


def strip_whitespace(v):
    return v.strip() if isinstance(v, str) else v


def upper(v):
    return v.strip().upper() if isinstance(v, str) else v


def lower(v):
    return v.strip().lower() if isinstance(v, str) else v


def title_case(v):
    return v.strip().title() if isinstance(v, str) else v


def digits_only(v):
    """Strips everything except digits. Good for phone numbers, IDs with
    inconsistent punctuation/formatting."""
    if not isinstance(v, str):
        return v
    return re.sub(r"\D", "", v)


def normalize_phone(v):
    """Normalizes any phone format down to a bare 10 (or 11 with country
    code) digit string for comparison purposes."""
    digits = digits_only(v)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits


def normalize_address(v):
    """Loose address normalization: uppercase, collapse whitespace, strip
    trailing punctuation, common abbreviation expansion could be added here."""
    if not isinstance(v, str):
        return v
    v = re.sub(r"\s+", " ", v.strip().upper())
    v = v.rstrip(".")
    return v


def alnum_only(v):
    if not isinstance(v, str):
        return v
    return re.sub(r"[^A-Za-z0-9]", "", v).upper()


def normalize_id(v):
    """Normalizes an identifier that may drift in FORMAT (not value) across
    systems -- dashes/spaces stripped, case-folded, and leading zeros
    dropped -- so 'E007', 'e-007', and '0007' are recognized as the same
    key. Used as the `key_transform` for matching records across sources,
    not just for display."""
    if v is None:
        return v
    s = alnum_only(v)
    stripped = s.lstrip("0")
    return stripped if stripped else s


def numeric(v):
    """Normalizes a currency/number-ish value (e.g. '$4,500.00', 4500, '4500')
    down to a float rounded to 2 decimals, so formatting differences
    ($ signs, commas, trailing .00) aren't flagged as mismatches. Returns
    None if the value can't be parsed as a number."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return round(float(v), 2)
    s = str(v).strip()
    if not s:
        return None
    s = re.sub(r"[^0-9.\-]", "", s)
    if not s or s in ("-", "."):
        return None
    try:
        return round(float(s), 2)
    except ValueError:
        return None


TRANSFORMS = {
    "none": none,
    "strip_whitespace": strip_whitespace,
    "upper": upper,
    "lower": lower,
    "title_case": title_case,
    "digits_only": digits_only,
    "normalize_phone": normalize_phone,
    "normalize_address": normalize_address,
    "alnum_only": alnum_only,
    "numeric": numeric,
    "normalize_id": normalize_id,
}


def apply_transform(name: str, value):
    fn = TRANSFORMS.get(name or "none", none)
    if value is None:
        return None
    return fn(value)
