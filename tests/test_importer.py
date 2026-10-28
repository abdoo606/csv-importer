from __future__ import annotations

import sqlite3

import pytest

from importer.loader import import_csv, infer_columns, read_rows
from importer.schema import ColumnType, coerce, safe_identifier, sqlite_type


# ----------------------------------------------------------------- schema
@pytest.mark.parametrize(
    "values,expected",
    [
        (["1", "2", "-3"], ColumnType.INTEGER),
        (["1.5", "2"], ColumnType.REAL),
        (["true", "no"], ColumnType.BOOLEAN),
        (["2024-01-02", "2024-12-31"], ColumnType.DATE),
        (["abc", "1"], ColumnType.TEXT),
        (["", "NA"], ColumnType.TEXT),
    ],
)
def test_type_inference(values, expected):
    assert ColumnType.infer(values) is expected


def test_inference_ignores_nulls():
    assert ColumnType.infer(["1", "", "NA", "3"]) is ColumnType.INTEGER


def test_coerce_success_cases():
    assert coerce(" 42 ", ColumnType.INTEGER).value == 42
    assert coerce("yes", ColumnType.BOOLEAN).value is True
    assert coerce("2024-05-06", ColumnType.DATE).value == "2024-05-06"


def test_coerce_failure_is_reported_not_raised():
    result = coerce("not-a-number", ColumnType.INTEGER)
    assert result.value is None and result.error


def test_nulls_become_none():
    for raw in ("", "NULL", "n/a", "-"):
        assert coerce(raw, ColumnType.TEXT).value is None


def test_identifier_sanitisation_blocks_injection():
    assert safe_identifier("Full Name!") == "full_name"
    assert safe_identifier("2024 Total") == "c_2024_total"
    with pytest.raises(ValueError):
        safe_identifier("!!!")


def test_sqlite_type_mapping():
    assert sqlite_type(ColumnType.BOOLEAN) == "INTEGER"
    assert sqlite_type(ColumnType.DATE) == "TEXT"


# ----------------------------------------------------------------- loader
@pytest.fixture()
def conn():
    connection = sqlite3.connect(":memory:")
    yield connection
    connection.close()


@pytest.fixture()
def csv_file(tmp_path):
    path = tmp_path / "people.csv"
    path.write_text(
        "Name,Age,Joined,Active\n"
        "Ada,36,2024-01-05,true\n"
        "Grace,45,2023-06-01,yes\n",
        encoding="utf-8",
    )
    return path


def test_import_creates_table_and_rows(csv_file, conn):
    report = import_csv(csv_file, conn, "people")
    assert report.rows_inserted == 2 and report.ok
    count = conn.execute("SELECT COUNT(*) FROM people").fetchone()[0]
    assert count == 2
    assert report.columns["age"] is ColumnType.INTEGER


def test_dry_run_writes_nothing(csv_file, conn):
    report = import_csv(csv_file, conn, "people", dry_run=True)
    assert report.rows_inserted == 2
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    assert tables == []


def test_bad_row_is_rejected_and_counted(tmp_path, conn):
    path = tmp_path / "bad.csv"
    path.write_text("Id,Score\n1,10\n2,oops\n3,30\n", encoding="utf-8")
    report = import_csv(path, conn, "scores", column_types={"score": ColumnType.INTEGER})
    assert report.rows_inserted == 2
    assert report.rows_rejected == 1
    assert not report.ok
    assert "line 3" in report.errors[0].__str__()


def test_strict_mode_raises(tmp_path, conn):
    path = tmp_path / "bad.csv"
    path.write_text("Id,Score\n1,10\n2,NaN\n", encoding="utf-8")
    with pytest.raises(ValueError):
        import_csv(
            path, conn, "strict", strict=True, column_types={"score": ColumnType.REAL}
        )


def test_utf8_bom_is_handled(tmp_path, conn):
    path = tmp_path / "bom.csv"
    path.write_bytes("Name\nAda\n".encode("utf-8-sig"))
    headers, _ = read_rows(path)
    assert headers == ["Name"]


def test_ragged_rows_do_not_crash(tmp_path, conn):
    path = tmp_path / "ragged.csv"
    path.write_text("A,B\n1,2\n3\n", encoding="utf-8")
    report = import_csv(path, conn, "ragged")
    assert report.rows_read == 2


def test_missing_header_row_raises(tmp_path, conn):
    path = tmp_path / "empty.csv"
    path.write_text("", encoding="utf-8")
    with pytest.raises(ValueError):
        import_csv(path, conn, "empty")


def test_summary_is_human_readable(csv_file, conn):
    assert "2 inserted" in import_csv(csv_file, conn, "people").summary()


def test_unknown_pinned_column_is_rejected(csv_file, conn):
    with pytest.raises(ValueError, match="unknown columns"):
        import_csv(csv_file, conn, "people", column_types={"nope": ColumnType.TEXT})


def test_nan_is_not_a_number():
    assert coerce("NaN", ColumnType.REAL).error
    assert coerce("inf", ColumnType.REAL).error
    assert ColumnType.infer(["NaN"]) is ColumnType.TEXT


def test_table_name_cannot_inject_sql(csv_file, conn):
    report = import_csv(csv_file, conn, "people; DROP TABLE people")
    assert report.table == "people_drop_table_people"
