"""Load CSV into SQLite with a summary report instead of exceptions-as-control-flow."""

from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from .schema import ColumnType, coerce, safe_identifier, sqlite_type


@dataclass(slots=True)
class RowError:
    line: int
    column: str
    message: str

    def __str__(self) -> str:
        return f"line {self.line}, {self.column}: {self.message}"


@dataclass(slots=True)
class ImportReport:
    table: str
    rows_read: int = 0
    rows_inserted: int = 0
    rows_rejected: int = 0
    columns: dict[str, ColumnType] = field(default_factory=dict)
    errors: list[RowError] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        lines = [
            f"table {self.table}: {self.rows_inserted} inserted, "
            f"{self.rows_rejected} rejected of {self.rows_read} read"
        ]
        lines += [f"  {c}: {t.value}" for c, t in self.columns.items()]
        lines += [f"  {e}" for e in self.errors[:10]]
        if len(self.errors) > 10:
            lines.append(f"  ... and {len(self.errors) - 10} more errors")
        return "\n".join(lines)


def read_rows(path: str | Path, *, encoding: str = "utf-8-sig") -> tuple[list[str], list[dict[str, str]]]:
    with Path(path).open(newline="", encoding=encoding) as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise ValueError("CSV has no header row")
        rows = [dict(row) for row in reader]
        return list(reader.fieldnames), rows


def infer_columns(headers: list[str], rows: list[dict[str, str]]) -> dict[str, ColumnType]:
    types: dict[str, ColumnType] = {}
    for header in headers:
        values = [row.get(header, "") for row in rows[:200]]  # sample for performance
        types[safe_identifier(header)] = ColumnType.infer(values)
    return types


def import_csv(
    path: str | Path,
    connection: sqlite3.Connection,
    table: str,
    *,
    dry_run: bool = False,
    strict: bool = False,
    column_types: dict[str, ColumnType] | None = None,
) -> ImportReport:
    """Inference samples the first 200 rows; pass ``column_types`` to pin a schema."""
    table_name = safe_identifier(table)
    headers, rows = read_rows(path)
    if column_types:
        columns = {safe_identifier(k): v for k, v in column_types.items()}
        unknown = set(columns) - {safe_identifier(h) for h in headers}
        if unknown:
            raise ValueError(f"column_types refers to unknown columns: {sorted(unknown)}")
    else:
        columns = infer_columns(headers, rows)
    report = ImportReport(table_name, columns=columns)
    header_map = {safe_identifier(h): h for h in headers}

    ddl = ", ".join(f'"{c}" {sqlite_type(t)}' for c, t in columns.items())
    if not dry_run:
        connection.execute(f'CREATE TABLE IF NOT EXISTS "{table_name}" ({ddl})')

    placeholders = ", ".join("?" for _ in columns)
    columns_sql = ", ".join(f'"{c}"' for c in columns)
    insert_sql = f'INSERT INTO "{table_name}" ({columns_sql}) VALUES ({placeholders})'

    for line, row in enumerate(rows, start=2):
        report.rows_read += 1
        values: list[object] = []
        row_failed = False
        for column, column_type in columns.items():
            result = coerce(row.get(header_map[column]) or "", column_type)
            if result.error:
                report.errors.append(RowError(line, column, result.error))
                row_failed = True
            values.append(result.value)
        if row_failed:
            report.rows_rejected += 1
            if strict:
                if not dry_run:
                    connection.rollback()
                raise ValueError(report.errors[-1].message)
            continue
        if not dry_run:
            connection.execute(insert_sql, values)
        report.rows_inserted += 1

    if not dry_run:
        connection.commit()
    return report
