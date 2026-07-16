"""Reusable field-validation engine (Phase 4, shared with Sheets).

Pure and UI-agnostic: given a :class:`FieldRule` and a value it returns a list of
human-readable error messages (empty when valid). The same engine backs both the
Form field validation and the Sheet cell validation.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from pydantic import BaseModel

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^\+?[0-9 ()\-]{6,}$")
_ZIP_RE = re.compile(r"^[0-9A-Za-z \-]{3,10}$")
_URL_RE = re.compile(r"^https?://[^\s]+$")


class FieldRule(BaseModel):
    """Declarative validation rules for a single field/column."""

    required: bool = False
    min: float | None = None  # numeric minimum
    max: float | None = None  # numeric maximum
    min_len: int | None = None  # minimum string length
    max_len: int | None = None  # maximum string length
    allowed_chars: str | None = None  # regex character class, e.g. "A-Za-z0-9"
    forbidden_chars: str | None = None  # regex character class to reject
    regex: str | None = None  # full-match pattern
    fmt: str | None = None  # "email"|"phone"|"zip"|"url"|"credit_card"
    date_not_before: str | None = None  # ISO date or "today"
    date_not_after: str | None = None  # ISO date or "today"
    message: str | None = None  # overrides all default messages


def _is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _to_number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if value == "today":
        return date.today()
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _luhn_ok(digits: str) -> bool:
    if not digits.isdigit() or len(digits) < 12:
        return False
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


def _check_format(fmt: str, text: str) -> str | None:
    """Return an error message if ``text`` does not match ``fmt``, else ``None``."""
    if fmt == "email" and not _EMAIL_RE.match(text):
        return "Email non valida."
    if fmt == "phone" and not _PHONE_RE.match(text):
        return "Numero di telefono non valido."
    if fmt == "zip" and not _ZIP_RE.match(text):
        return "CAP/ZIP non valido."
    if fmt == "url" and not _URL_RE.match(text):
        return "URL non valido."
    if fmt == "credit_card" and not _luhn_ok(re.sub(r"[ \-]", "", text)):
        return "Numero di carta di credito non valido."
    return None


def validate_field(rule: FieldRule, value: Any) -> list[str]:
    """Validate ``value`` against ``rule``; return a list of error messages.

    If ``rule.message`` is set and any check fails, it replaces the default
    messages with that single custom message.
    """
    errors: list[str] = []

    if _is_empty(value):
        if rule.required:
            errors.append("Campo obbligatorio.")
        return [rule.message] if (errors and rule.message) else errors

    text = str(value)

    if rule.min is not None or rule.max is not None:
        num = _to_number(value)
        if num is None:
            errors.append("Deve essere un numero.")
        else:
            if rule.min is not None and num < rule.min:
                errors.append(f"Deve essere ≥ {rule.min:g}.")
            if rule.max is not None and num > rule.max:
                errors.append(f"Deve essere ≤ {rule.max:g}.")

    if rule.min_len is not None and len(text) < rule.min_len:
        errors.append(f"Lunghezza minima {rule.min_len}.")
    if rule.max_len is not None and len(text) > rule.max_len:
        errors.append(f"Lunghezza massima {rule.max_len}.")

    if rule.allowed_chars and re.search(f"[^{rule.allowed_chars}]", text):
        errors.append("Contiene caratteri non ammessi.")
    if rule.forbidden_chars and re.search(f"[{rule.forbidden_chars}]", text):
        errors.append("Contiene caratteri vietati.")

    if rule.regex and not re.fullmatch(rule.regex, text):
        errors.append("Formato non valido.")

    if rule.fmt:
        msg = _check_format(rule.fmt, text)
        if msg:
            errors.append(msg)

    if rule.date_not_before or rule.date_not_after:
        dvalue = _to_date(value)
        if dvalue is None:
            errors.append("Data non valida.")
        else:
            lo = _to_date(rule.date_not_before) if rule.date_not_before else None
            hi = _to_date(rule.date_not_after) if rule.date_not_after else None
            if lo and dvalue < lo:
                errors.append(f"Non prima di {lo.isoformat()}.")
            if hi and dvalue > hi:
                errors.append(f"Non dopo {hi.isoformat()}.")

    return [rule.message] if (errors and rule.message) else errors
