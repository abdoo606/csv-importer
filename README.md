# 10 · importer

Defensive CSV → SQLite loading with type inference, a dry run and a report.

## Run

```bash
python -m importer --help  (or import importer.loader)
```

## Test

```bash
pytest projects/10-csv-importer -q
```

## What it demonstrates

- Bad rows are rejected and reported, not thrown - the pipeline keeps going
- Column types inferred from a 200-row sample, or pinned explicitly
- Header and table names sanitised to block SQL injection
- `NaN`/`inf` rejected: they parse as floats but poison a numeric column

## Repository
- GitHub: https://github.com/{owner}/csv-importer
- Python 3.11+ · tests: `pytest` · runtime dependencies: none (standard library only)
