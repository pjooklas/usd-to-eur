from datetime import date
from decimal import Decimal

import pymupdf as fitz
import pytest

from invoice_converter.conversion import convert_usd_to_eur
from invoice_converter.extraction import InvoiceExtractionError, extract_invoice_details, extract_invoice_fields
from invoice_converter.pdf_output import build_converted_pdf
from invoice_converter.rates import ExchangeRate, ExchangeRateError, _parse_records, select_latest_prior_rate


def make_invoice(text: str) -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    data = document.tobytes()
    document.close()
    return data


def test_extracts_issue_date_and_grand_total():
    details = extract_invoice_details(make_invoice("Invoice Date: 2026-10-07\nGrand Total USD 1,234.50"))
    assert details.issue_date == date(2026, 10, 7)
    assert details.usd_total == Decimal("1234.50")


def test_extracts_deel_invoice_month_name_date_and_split_total():
    invoice_text = """INVOICE
Issue Date June 25, 2026
TOTAL
USD $2,609.32
Subtotal USD $2,609.32
VAT (0%) USD $0
Total USD $2,609.32"""
    details = extract_invoice_details(make_invoice(invoice_text))
    assert details.issue_date == date(2026, 6, 25)
    assert details.usd_total == Decimal("2609.32")


def test_extracts_total_amount_on_following_line():
    details = extract_invoice_details(make_invoice("Issue Date June 25, 2026\nTotal\nUSD $2,609.32"))
    assert details.issue_date == date(2026, 6, 25)
    assert details.usd_total == Decimal("2609.32")


def test_rejects_scanned_pdf_without_text():
    with pytest.raises(InvoiceExtractionError, match="No selectable text"):
        extract_invoice_details(make_invoice(""))


def test_rejects_conflicting_invoice_totals():
    pdf = make_invoice("Invoice Date: 2026-10-07\nTotal USD 120.00\nGrand Total USD 100.00")
    with pytest.raises(InvoiceExtractionError, match="ambiguous"):
        extract_invoice_details(pdf)


def test_extraction_leaves_ambiguous_values_for_manual_review():
    pdf = make_invoice("Total USD 120.00\nGrand Total USD 100.00")
    fields = extract_invoice_fields(pdf)
    assert fields.issue_date is None
    assert fields.usd_total is None
    assert len(fields.warnings) == 2


def test_conversion_uses_half_up_cent_rounding():
    assert convert_usd_to_eur(Decimal("100"), Decimal("1.1177")) == Decimal("89.47")
    assert convert_usd_to_eur(Decimal("1"), Decimal("8")) == Decimal("0.13")


def test_parses_lietuvos_bankas_rates_and_selects_prior_date():
    xml = b"""<FxRates xmlns=\"http://www.lb.lt/WebServices/FxRates\">
    <FxRate><Tp>EU</Tp><Dt>2026-10-05</Dt><CcyAmt><Ccy>EUR</Ccy><Amt>1</Amt></CcyAmt><CcyAmt><Ccy>USD</Ccy><Amt>1.1200</Amt></CcyAmt></FxRate>
    <FxRate><Tp>EU</Tp><Dt>2026-10-07</Dt><CcyAmt><Ccy>EUR</Ccy><Amt>1</Amt></CcyAmt><CcyAmt><Ccy>USD</Ccy><Amt>1.1177</Amt></CcyAmt></FxRate></FxRates>"""
    rates = _parse_records(xml)
    selected = select_latest_prior_rate(rates, date(2026, 10, 6))
    assert selected.rate_date == date(2026, 10, 5)
    assert selected.usd_per_eur == Decimal("1.1200")


def test_prior_rate_selection_fails_if_all_rates_are_in_the_future():
    rates = [ExchangeRate(date(2026, 10, 7), Decimal("1.1177"))]
    with pytest.raises(ExchangeRateError, match="on or before"):
        select_latest_prior_rate(rates, date(2026, 10, 6))


def test_rate_parser_rejects_invalid_xml():
    with pytest.raises(ExchangeRateError, match="invalid XML"):
        _parse_records(b"<invalid")


def test_output_pdf_adds_rate_and_eur_total_under_usd_total():
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    page.insert_text((420, 185), "TOTAL", fontsize=10, fontname="hebo")
    page.insert_text((390, 210), "USD $100.00", fontsize=18, fontname="hebo")
    original = document.tobytes()
    document.close()
    output = build_converted_pdf(
        original,
        date(2026, 10, 7),
        Decimal("100.00"),
        Decimal("1.1177"),
        date(2026, 10, 7),
        Decimal("89.47"),
    )
    result = fitz.open(stream=output, filetype="pdf")
    assert result.page_count == 1
    page_text = result[0].get_text()
    assert "USD $100.00" in page_text
    assert "Rate (2026-10-07): 1 EUR = 1.1177 USD" in page_text
    assert "Total in EUR: EUR 89.47" in page_text
    amount_rect = result[0].search_for("USD $100.00")[0]
    rate_rect = result[0].search_for("Rate (2026-10-07): 1 EUR = 1.1177 USD")[0]
    amount_bottom = amount_rect.y1
    rate_top = rate_rect.y0
    assert rate_top >= amount_bottom
    assert abs(rate_rect.x1 - amount_rect.x1) < 1
    spans = [
        span
        for block in result[0].get_text("dict")["blocks"]
        for line in block.get("lines", [])
        for span in line["spans"]
    ]
    amount_span = next(span for span in spans if "USD $100.00" in span["text"])
    rate_span = next(span for span in spans if "Rate (2026-10-07)" in span["text"])
    assert bool(rate_span["flags"] & 16) == bool(amount_span["flags"] & 16)
    assert rate_span["color"] == amount_span["color"]