# heavymetal/tests/test_imports.py
"""The /import/ HAE CSV route + shared upload validation."""

import io
from datetime import date

from backend.routes.imports import _find_date_column, _import_csv


def test_import_form_renders(client):
    assert client.get("/import/").status_code == 200


def test_find_date_column_falls_back_to_first():
    # no column named date/datetime/timestamp -> the first column is used.
    assert _find_date_column(["When", "Weight & Body Mass (lb)"]) == "When"
    assert _find_date_column(["Date", "Steps"]) == "Date"
    assert _find_date_column([]) is None


def test_import_csv_no_mapped_columns_errors(db_session):
    summary = _import_csv("Date,Mystery Column\n2031-01-01,5\n")
    assert "No recognizable metric columns" in summary.get("error", "")


def test_import_csv_handles_bad_rows(db_session):
    # one CSV exercising bad date, empty cell, non-numeric cell, an out-of-range
    # rejection, a fully-skipped row, and good writes.
    csv = (
        "Date,Weight & Body Mass (lb),Protein (g)\n"
        "not-a-date,200,150\n"  # bad date -> whole row skipped
        "2031-03-01,,abc\n"  # empty + non-numeric -> nothing written -> skipped
        "2031-03-02,25.0,150\n"  # weight 25 rejected; protein 150 added
        "2031-03-03,201,150\n"  # both good
    )
    summary = _import_csv(csv)
    assert summary["bad_dates"] == 1
    assert summary["rejected"] == 1
    assert summary["skipped_rows"] == 1
    assert summary["added"] >= 1


def test_import_route_flashes_error_for_unmapped_csv(client):
    r = client.post(
        "/import/",
        data={"csv_file": (io.BytesIO(b"Date,Mystery\n2031-01-01,5\n"), "x.csv")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"No recognizable metric columns" in r.data


def test_import_rejects_missing_and_wrong_type(client):
    r = client.post(
        "/import/", data={}, content_type="multipart/form-data", follow_redirects=True
    )
    assert b"Choose a CSV file to import." in r.data

    r = client.post(
        "/import/",
        data={"csv_file": (io.BytesIO(b"x"), "foo.txt")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"Please upload a .csv file." in r.data


def test_import_valid_csv_writes_measurement(client, db_session):
    from backend.models import Measurement

    csv = b"Date,Weight & Body Mass (lb)\n2031-08-08 00:00:00,202.0\n"
    r = client.post(
        "/import/",
        data={"csv_file": (io.BytesIO(csv), "hae.csv")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"Import complete" in r.data

    m = Measurement.query.filter_by(
        user_id=1, date=date(2031, 8, 8), measurement_type="weight", unit="lbs"
    ).first()
    assert m is not None and float(m.value) == 202.0
