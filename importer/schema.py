"""Column type inference and coercion. Everything is explicit and reversible."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
NULLS = {"", "null", "none", "na", "n/a", "-"}


class ColumnType(str, Enum):
    INTEGER = "INTEGER"
    REAL = "REAL"
    TEXT = "TEXT"
    BOOLEAN = "BOOLEAN"
    DATE = "DATE"

    @classmethod
    def infer(cls, values: list[str]) -> "ColumnType":
        present = [v.strip() for v in values if (v or "").strip().lower() not in NULLS]
        if not present:
            return cls.TEXT
        if all(_is_int(v) for v in present):
            return cls.INTEGER
        if all(_is_float(v) for v in present):
            return cls.REAL
        if all(v.lower() in {"true", "false", "yes", "no", "1", "0"} for v in present):
            return cls.BOOLEAN
        if all(ISO_DATE.match(v) for v in present):
            return cls.DATE
        return cls.TEXT


def _is_int(value: str) -> bool:
    try:
        int(value)
        return True
    except ValueError:
        return False


def _is_float(value: str) -> bool:
    """'nan' and 'inf' parse as floats but are not usable numbers - reject them."""
    try:
        return math.isfinite(float(value))
    except ValueError:
        return False


@dataclass(slots=True, frozen=True)
class CoercionResult:
    value: object
    error: str | None = None


def coerce(raw: str | None, column_type: ColumnType) -> CoercionResult:
    text = (raw or "").strip()
    if text.lower() in NULLS:
        return CoercionResult(None)
    try:
        if column_type is ColumnType.INTEGER:
            return CoercionResult(int(text))
        if column_type is ColumnType.REAL:
            number = float(text)
            if not math.isfinite(number):
                return CoercionResult(None, f"{raw!r} is not a finite number")
            return CoercionResult(number)
        if column_type is ColumnType.BOOLEAN:
            return CoercionResult(text.lower() in {"true", "yes", "1"})
        if column_type is ColumnType.DATE:
            return CoercionResult(date.fromisoformat(text).isoformat())
        return CoercionResult(text)
    except (ValueError, TypeError):
        return CoercionResult(None, f"{raw!r} is not a valid {column_type.value}")


def sqlite_type(column_type: ColumnType) -> str:
    return {
        ColumnType.INTEGER: "INTEGER",
        ColumnType.REAL: "REAL",
        ColumnType.BOOLEAN: "INTEGER",  # sqlite has no native boolean
        ColumnType.DATE: "TEXT",  # ISO-8601 sorts lexicographically
        ColumnType.TEXT: "TEXT",
    }[column_type]


def safe_identifier(name: str) -> str:
    """Prevents SQL injection through header names used as column names."""
    cleaned = re.sub(r"\W+", "_", name.strip()).strip("_").lower()
    if not cleaned:
        raise ValueError(f"cannot derive a column name from {name!r}")
    if cleaned[0].isdigit():
        cleaned = f"c_{cleaned}"
    return cleaned
