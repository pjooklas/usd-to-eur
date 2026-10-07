from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

import requests


SERVICE_URL = "https://www.lb.lt/webservices/fxrates/FxRates.asmx/getFxRatesForCurrency"
SOURCE_URL = "https://www.lb.lt/lt/kasdien-skelbiami-euro-ir-uzsienio-valiutu-santykiai-skelbia-europos-centrinis-bankas"


class ExchangeRateError(RuntimeError):
    """Raised when Lietuvos bankas rates cannot be retrieved or parsed."""


@dataclass(frozen=True)
class ExchangeRate:
    rate_date: date
    usd_per_eur: Decimal


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _parse_records(payload: bytes | str) -> list[ExchangeRate]:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise ExchangeRateError("Lietuvos bankas returned invalid XML.") from exc

    result = next((node for node in root.iter() if _local_name(node.tag) == "getfxratesforcurrencyresult"), None)
    if result is not None and result.text and result.text.strip():
        try:
            root = ET.fromstring(result.text.strip())
        except ET.ParseError:
            pass

    records: list[ExchangeRate] = []
    for node in root.iter():
        if _local_name(node.tag) != "fxrate":
            continue
        rate_date = next(
            ((child.text or "").strip() for child in node if _local_name(child.tag) in {"dt", "date"}),
            "",
        )
        currency_amounts = [
            child for child in node if _local_name(child.tag) in {"ccyamt", "currencyamount"}
        ]
        if not currency_amounts:
            currency_amounts = [node]
        usd_amount = None
        for currency_amount in currency_amounts:
            values = {_local_name(child.tag): (child.text or "").strip() for child in currency_amount}
            if (values.get("ccy") or values.get("currency")) == "USD":
                usd_amount = values.get("amt") or values.get("amount")
                break
        if not rate_date or not usd_amount:
            continue
        try:
            parsed_date = date.fromisoformat(rate_date[:10])
            parsed_amount = Decimal(usd_amount.replace(",", "."))
        except (ValueError, InvalidOperation):
            continue
        if parsed_amount > 0:
            records.append(ExchangeRate(parsed_date, parsed_amount))
    return records


def select_latest_prior_rate(records: list[ExchangeRate], issue_date: date) -> ExchangeRate:
    eligible = [record for record in records if record.rate_date <= issue_date]
    if not eligible:
        raise ExchangeRateError("No published USD rate was found on or before the invoice issue date.")
    return max(eligible, key=lambda record: record.rate_date)


def fetch_usd_rate(issue_date: date, session: requests.Session | None = None) -> ExchangeRate:
    client = session or requests.Session()
    params = {
        "tp": "EU",
        "ccy": "USD",
        "dtFrom": (issue_date - timedelta(days=10)).isoformat(),
        "dtTo": issue_date.isoformat(),
    }
    try:
        response = client.get(SERVICE_URL, params=params, timeout=15)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ExchangeRateError("Could not reach the Lietuvos bankas exchange-rate service.") from exc

    return select_latest_prior_rate(_parse_records(response.content), issue_date)
