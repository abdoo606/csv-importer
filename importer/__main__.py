"""CLI: python -m importer data.csv --table people [--dry-run]"""
from __future__ import annotations

import argparse
import sqlite3
import sys

from .loader import import_csv


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="importer")
    parser.add_argument("csvfile")
    parser.add_argument("--table", required=True)
    parser.add_argument("--db", default="imported.db")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    connection = sqlite3.connect(args.db)
    try:
        report = import_csv(args.csvfile, connection, args.table, dry_run=args.dry_run, strict=args.strict)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        connection.close()
    print(report.summary())
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
