from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

import pymupdf as fitz

from invoice_converter.rates import SOURCE_URL

_NUMBER = re.compile(r"(?<![\d./])\d[\d,]*(?:\.\d{1,2})?(?![\d./])")


def _find_total_anchor(document: fitz.Document, usd_total: Decimal):
    best = None
    best_rank = None
    for page_number, page in enumerate(document):
        blocks = page.get_text("dict").get("blocks", [])
        for block in blocks:
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                matching_spans = []
                for span in spans:
                    for value in _NUMBER.findall(span.get("text", "")):
                        try:
                            if Decimal(value.replace(",", "")) == usd_total:
                                matching_spans.append(span)
                                break
                        except InvalidOperation:
                            continue
                if not matching_spans:
                    continue

                style_span = max(matching_spans, key=lambda span: span.get("size", 0))
                line_text = " ".join(span.get("text", "") for span in spans)
                line_rect = fitz.Rect(line["bbox"])
                rank = (
                    style_span.get("size", 0),
                    int(bool(re.search(r"\bUSD\b|US\$|\$", line_text, re.IGNORECASE))),
                    -page_number,
                    -line_rect.y0,
                )
                if best_rank is None or rank > best_rank:
                    best_rank = rank
                    best = (page, line_rect, style_span)
    return best


def _add_conversion_lines(
    document: fitz.Document,
    issue_date: date,
    usd_total: Decimal,
    usd_per_eur: Decimal,
    rate_date: date,
    eur_total: Decimal,
) -> bool:
    anchor = _find_total_anchor(document, usd_total)
    if anchor is None:
        return False

    page, anchor_rect, style_span = anchor
    is_bold = bool(style_span.get("flags", 0) & 16)
    font_name = "hebo" if is_bold else "helv"
    font_size = min(10.5, max(8, style_span.get("size", 12) * 0.65))
    color_value = style_span.get("color", 0)
    color = tuple(((color_value >> shift) & 255) / 255 for shift in (16, 8, 0))
    rate_line = f"Rate ({rate_date.isoformat()}): 1 EUR = {usd_per_eur} USD"
    total_line = f"Total in EUR: EUR {eur_total:,.2f}"
    lines = f"{rate_line}\n{total_line}"
    text_width = max(
        fitz.get_text_length(rate_line, fontname=font_name, fontsize=font_size),
        fitz.get_text_length(total_line, fontname=font_name, fontsize=font_size),
    ) + 4
    right = min(anchor_rect.x1, page.rect.width - 18)
    left = max(18, right - text_width)
    line_height = font_size * 1.35
    box_height = line_height * 2
    first_top = anchor_rect.y1 + max(3, font_size * 0.25)

    for offset in range(6):
        top = first_top + offset * font_size * 0.55
        box = fitz.Rect(left, top, right, top + box_height)
        if box.y1 > page.rect.height - 12:
            break
        overlaps_text = any(
            box.intersects(fitz.Rect(span["bbox"]))
            for block in page.get_text("dict").get("blocks", [])
            for line in block.get("lines", [])
            for span in line.get("spans", [])
        )
        if overlaps_text:
            continue
        spare_space = page.insert_textbox(
            box,
            lines,
            fontname=font_name,
            fontsize=font_size,
            color=color,
            align=fitz.TEXT_ALIGN_RIGHT,
            lineheight=1.2,
        )
        if spare_space >= 0:
            return True
    return False


def _append_conversion_page(
    document: fitz.Document,
    issue_date: date,
    usd_total: Decimal,
    usd_per_eur: Decimal,
    rate_date: date,
    eur_total: Decimal,
) -> None:
    page = document.new_page(width=595, height=842)
    page.insert_text((54, 70), "USD TO EUR INVOICE CONVERSION", fontsize=18, fontname="hebo")
    page.insert_text((54, 112), f"Invoice issue date: {issue_date.isoformat()}", fontsize=11)
    page.insert_text((54, 142), f"Original invoice total: USD {usd_total:,.2f}", fontsize=13)
    page.insert_text((54, 170), f"Exchange rate date: {rate_date.isoformat()}", fontsize=11)
    page.insert_text((54, 195), f"Official rate: 1 EUR = {usd_per_eur} USD", fontsize=11)
    page.insert_text((54, 235), f"Converted invoice total: EUR {eur_total:,.2f}", fontsize=16, fontname="hebo")
    page.draw_line((54, 255), (541, 255), color=(0.25, 0.38, 0.33), width=1)
    page.insert_text((54, 281), "Source: Lietuvos bankas (ECB reference rates)", fontsize=10)
    page.insert_text((54, 300), SOURCE_URL, fontsize=7)

def build_converted_pdf(
    original_pdf: bytes,
    issue_date: date,
    usd_total: Decimal,
    usd_per_eur: Decimal,
    rate_date: date,
    eur_total: Decimal,
) -> bytes:
    document = fitz.open(stream=original_pdf, filetype="pdf")
    placed_in_invoice = _add_conversion_lines(
        document, issue_date, usd_total, usd_per_eur, rate_date, eur_total
    )
    if not placed_in_invoice:
        _append_conversion_page(document, issue_date, usd_total, usd_per_eur, rate_date, eur_total)
    output = document.tobytes(deflate=True)
    document.close()
    return output
