from decimal import Decimal, ROUND_HALF_UP


CENT = Decimal("0.01")


def convert_usd_to_eur(usd_total: Decimal, usd_per_eur: Decimal) -> Decimal:
    if usd_total <= 0 or usd_per_eur <= 0:
        raise ValueError("The invoice total and exchange rate must be greater than zero.")
    return (usd_total / usd_per_eur).quantize(CENT, rounding=ROUND_HALF_UP)
