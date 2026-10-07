from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename

sys.path.insert(0, str(Path(__file__).parent / "src"))

from invoice_converter.conversion import convert_usd_to_eur
from invoice_converter.extraction import InvoiceExtractionError, extract_invoice_fields
from invoice_converter.pdf_output import build_converted_pdf
from invoice_converter.rates import ExchangeRateError, fetch_usd_rate


MAX_UPLOAD_BYTES = 20 * 1024 * 1024
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES


def _read_invoice() -> tuple[bytes, str]:
    upload = request.files.get("invoice")
    if upload is None or not upload.filename:
        raise ValueError("Choose an invoice PDF to continue.")
    try:
        pdf_bytes = upload.stream.read(MAX_UPLOAD_BYTES + 1)
    finally:
        upload.close()
    if len(pdf_bytes) > MAX_UPLOAD_BYTES:
        raise ValueError("The PDF is larger than the 20 MB upload limit.")
    if not pdf_bytes.startswith(b"%PDF-"):
        raise ValueError("That file does not look like a PDF. Choose a valid invoice PDF.")
    return pdf_bytes, upload.filename


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/inspect")
def inspect_invoice():
    try:
        pdf_bytes, _ = _read_invoice()
        fields = extract_invoice_fields(pdf_bytes)
    except (ValueError, InvoiceExtractionError) as error:
        return jsonify(error=str(error)), 400
    return jsonify(
        issue_date=fields.issue_date.isoformat() if fields.issue_date else "",
        usd_total=format(fields.usd_total, "f") if fields.usd_total is not None else "",
        warnings=fields.warnings,
    )


@app.post("/convert")
def convert_invoice():
    try:
        pdf_bytes, original_name = _read_invoice()
        issue_date = date.fromisoformat(request.form.get("issue_date", "").strip())
        usd_total = Decimal(request.form.get("usd_total", "").replace(",", "").replace("$", "").strip())
        if not usd_total.is_finite() or usd_total <= 0:
            raise ValueError("Enter a USD total greater than zero.")
        rate = fetch_usd_rate(issue_date)
        eur_total = convert_usd_to_eur(usd_total, rate.usd_per_eur)
        result = build_converted_pdf(
            pdf_bytes, issue_date, usd_total, rate.usd_per_eur, rate.rate_date, eur_total
        )
    except (InvalidOperation, ValueError) as error:
        return jsonify(error=f"Check the invoice details: {error}"), 400
    except ExchangeRateError as error:
        return jsonify(error=str(error)), 502

    clean_name = secure_filename(original_name) or "invoice.pdf"
    response = send_file(
        BytesIO(result),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"{Path(clean_name).stem} EUR.pdf",
    )
    response.headers["X-Rate-Date"] = rate.rate_date.isoformat()
    response.headers["X-USD-Per-EUR"] = format(rate.usd_per_eur, "f")
    response.headers["X-USD-Total"] = format(usd_total, "f")
    response.headers["X-EUR-Total"] = format(eur_total, "f")
    return response


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
