"""Money formatting helpers (Indian digit grouping for INR)."""

from __future__ import annotations

SYMBOLS = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥", "AUD": "A$", "CAD": "C$", "SGD": "S$",
           "NZD": "NZ$", "AED": "AED ", "SAR": "SAR ", "CHF": "CHF ", "QAR": "QAR ", "OMR": "OMR ", "BHD": "BHD ",
           "KWD": "KWD ", "ZAR": "R ", "SEK": "SEK ", "NOK": "NOK ", "DKK": "DKK ", "PLN": "PLN ", "MYR": "RM ",
           "KES": "KES ", "LKR": "LKR "}


def _indian_group(integer: str) -> str:
    if len(integer) <= 3:
        return integer
    head, tail = integer[:-3], integer[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts) + "," + tail


def fmt(amount: float, currency: str, decimals: int = 2, symbol: bool = True) -> str:
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    text = f"{amount:,.{decimals}f}"
    if currency == "INR":
        integer, _, frac = f"{amount:.{decimals}f}".partition(".")
        text = _indian_group(integer) + (f".{frac}" if frac else "")
    prefix = SYMBOLS.get(currency, currency + " ") if symbol else ""
    return f"{sign}{prefix}{text}"


def round_to(amount: float, decimals: int) -> float:
    return round(amount + 0.0, decimals)
