# heavymetal/backend/uploads.py
"""Shared helper for CSV file uploads (HAE import, Strong import)."""

from flask import flash, request


def read_uploaded_csv(field="csv_file", label="a CSV file"):
    """Return the decoded text of an uploaded .csv, or None after flashing why.

    Caller renders its own template on None:
        text = read_uploaded_csv("csv_file", "a CSV file")
        if text is None:
            return render_template("imports/form.html", summary=None)
    """
    f = request.files.get(field)
    if f is None or f.filename == "":
        flash(f"Choose {label} to import.", "error")
        return None
    if not f.filename.lower().endswith(".csv"):
        flash("Please upload a .csv file.", "error")
        return None
    raw = f.read()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("latin-1")
