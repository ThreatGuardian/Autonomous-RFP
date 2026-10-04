"""Money formatting helpers (Indian digit grouping and lakh / crore for INR)."""

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


def fmt_amount(amount: float, currency: str) -> str:
    """Readable large amount: lakh / crore for INR, thousand / million elsewhere."""
    if currency == "INR":
        if amount >= 1e7:
            return f"₹{amount / 1e7:,.2f} crore"
        if amount >= 1e5:
            return f"₹{amount / 1e5:,.2f} lakh"
        return fmt(amount, currency, 0)
    prefix = SYMBOLS.get(currency, currency + " ")
    if amount >= 1e9:
        return f"{prefix}{amount / 1e9:,.2f} billion"
    if amount >= 1e6:
        return f"{prefix}{amount / 1e6:,.2f} million"
    return fmt(amount, currency, 0)
