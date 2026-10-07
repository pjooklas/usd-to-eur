from datetime import date
from decimal import Decimal
from io import BytesIO

import pymupdf as fitz

import app as web_app
from invoice_converter.rates import ExchangeRate


def make_pdf(text: str) -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    result = document.tobytes()
    document.close()
    return result


def make_client():
    web_app.app.config.update(TESTING=True)
    return web_app.app.test_client()


def test_home_page_has_upload_and_review_workflow():
    response = make_client().get("/")
    assert response.status_code == 200
    assert b"Choose your invoice" in response.data
    assert b"Confirm the invoice details" in response.data
    assert b"Issue date" in response.data


def test_inspect_returns_detected_fields_for_confirmation():
    response = make_client().post(
        "/inspect",
        data={"invoice": (BytesIO(make_pdf("Invoice Date: 2026-10-07\nGrand Total USD 100.00")), "invoice.pdf")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    assert response.json["issue_date"] == "2026-10-07"
    assert response.json["usd_total"] == "100.00"
    assert response.json["warnings"] == []


def test_inspect_rejects_non_pdf_upload():
    response = make_client().post(
        "/inspect",
        data={"invoice": (BytesIO(b"not a pdf"), "invoice.pdf")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    assert "does not look like a PDF" in response.json["error"]


def test_convert_returns_original_pages_and_rate_metadata(monkeypatch):
    monkeypatch.setattr(
        web_app,
        "fetch_usd_rate",
        lambda issue_date: ExchangeRate(date(2026, 10, 7), Decimal("1.1177")),
    )
    response = make_client().post(
        "/convert",
        data={
            "invoice": (BytesIO(make_pdf("Original invoice page")), "deel-june-2026.pdf"),
            "issue_date": "2026-10-07",
            "usd_total": "100.00",
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    assert response.headers["Content-Disposition"] == 'attachment; filename="deel-june-2026 EUR.pdf"'
    assert response.headers["X-Rate-Date"] == "2026-10-07"
    assert response.headers["X-EUR-Total"] == "89.47"
    output = fitz.open(stream=response.data, filetype="pdf")
    assert output.page_count == 2
    assert "Original invoice page" in output[0].get_text()
    assert "EUR 89.47" in output[1].get_text()
