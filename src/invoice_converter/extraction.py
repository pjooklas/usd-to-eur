from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import pymupdf as fitz


class InvoiceExtractionError(ValueError):
    """Raised when a PDF does not contain an unambiguous text invoice."""


@dataclass(frozen=True)
class InvoiceDetails:
    issue_date: date
    usd_total: Decimal


@dataclass(frozen=True)
class InvoiceFields:
    issue_date: date | None
    usd_total: Decimal | None
    warnings: tuple[str, ...]


_MONTH = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
_DATE = (
    rf"(\d{{4}}-\d{{1,2}}-\d{{1,2}}|\d{{1,2}}[./-]\d{{1,2}}[./-]\d{{2,4}}"
    rf"|{_MONTH}\.?\s+\d{{1,2}},?\s+\d{{4}}|\d{{1,2}}\s+{_MONTH}\.?\s+\d{{4}})"
)
_DATE_LABEL = re.compile(
    rf"(?:invoice\s+date|date\s+of\s+issue|issue\s+date|issued\s+on)\s*:?\s*{_DATE}",
    re.IGNORECASE,
)
_TOTAL_LABEL = re.compile(
    r"(?:grand\s+total|invoice\s+total|total\s+amount|amount\s+due|total\s+due|total)\b[^\n\r]*",
    re.IGNORECASE,
)
_AMOUNT = re.compile(
    r"(?<![\w/.-])(?:USD\s*|US\$\s*|\$\s*)?"
    r"(-?\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|-?\d+(?:\.\d{1,2})?)"
    r"(?:\s*(?:USD|US\$))?(?![\w/.-])",
    re.IGNORECASE,
)


def _parse_date(value: str) -> date:
    for pattern in (
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m-%d-%Y",
        "%m.%d.%Y",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d.%m.%Y",
        "%m/%d/%y",
        "%d.%m.%y",
        "%B %d, %Y",
        "%b %d, %Y",
        "%B %d %Y",
        "%b %d %Y",
        "%d %B %Y",
        "%d %b %Y",
    ):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            continue
    raise InvoiceExtractionError(f"Could not interpret invoice date: {value}")


def _parse_usd_amount(value: str) -> Decimal:
    normalized = value.replace(",", "")
    try:
        amount = Decimal(normalized)
    except InvalidOperation as exc:
        raise InvoiceExtractionError("Could not interpret the USD total.") from exc
    if amount <= 0:
        raise InvoiceExtractionError("The USD total must be greater than zero.")
    return amount


def extract_invoice_fields(pdf_bytes: bytes) -> InvoiceFields:
    try:
        document = fitz.open(stream=pdf_bytes, filetype="pdf")
        text = "\n".join(page.get_text() for page in document)
    except Exception as exc:
        raise InvoiceExtractionError("The uploaded file is not a readable PDF.") from exc

    if not text.strip():
        raise InvoiceExtractionError("No selectable text was found. Scanned PDFs are not supported yet.")

    date_matches = _DATE_LABEL.findall(text)
    try:
        unique_dates = {_parse_date(item) for item in date_matches}
    except InvoiceExtractionError:
        unique_dates = set()
    warnings: list[str] = []
    issue_date = next(iter(unique_dates)) if len(unique_dates) == 1 else None
    if issue_date is None:
        reason = "No issue date was found" if not unique_dates else "More than one issue date was found"
        warnings.append(f"{reason}. Enter or confirm the invoice issue date manually.")

    totals: set[Decimal] = set()
    lines = text.splitlines()
    for line_index, line in enumerate(lines):
        for line_match in _TOTAL_LABEL.finditer(line):
            label_and_amount = line_match.group(0)
            if re.search(r"\b(subtotal|tax total|vat total|total tax)\b", label_and_amount, re.IGNORECASE):
                continue
            if not _AMOUNT.search(label_and_amount) and line_index + 1 < len(lines):
                next_line = lines[line_index + 1].strip()
                if re.match(r"^(?:USD\b|US\$|\$|\d)", next_line, re.IGNORECASE):
                    label_and_amount = f"{label_and_amount} {next_line}"
            amounts = _AMOUNT.findall(label_and_amount)
            if amounts:
                totals.add(_parse_usd_amount(amounts[-1]))
    usd_total = next(iter(totals)) if len(totals) == 1 else None
    if usd_total is None:
        reason = "No total amount was found" if not totals else "The total amount is ambiguous"
        warnings.append(f"{reason}. Enter or confirm the invoice total manually.")

    return InvoiceFields(issue_date=issue_date, usd_total=usd_total, warnings=tuple(warnings))


def extract_invoice_details(pdf_bytes: bytes) -> InvoiceDetails:
    fields = extract_invoice_fields(pdf_bytes)
    if fields.issue_date is None or fields.usd_total is None:
        raise InvoiceExtractionError(" ".join(fields.warnings))
    return InvoiceDetails(issue_date=fields.issue_date, usd_total=fields.usd_total)
