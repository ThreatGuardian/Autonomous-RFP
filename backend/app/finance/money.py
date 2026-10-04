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


# --------------------------------------------------------------------------- amount in words

_ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve",
         "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]
# (major unit, minor unit, minor units per major); currencies not listed use their ISO code.
CURRENCY_WORDS: dict[str, tuple[str, str | None, int]] = {
    "INR": ("Rupees", "Paise", 100), "USD": ("US Dollars", "Cents", 100), "EUR": ("Euros", "Cents", 100),
    "GBP": ("Pounds Sterling", "Pence", 100), "AED": ("UAE Dirhams", "Fils", 100), "SGD": ("Singapore Dollars", "Cents", 100),
    "AUD": ("Australian Dollars", "Cents", 100), "CAD": ("Canadian Dollars", "Cents", 100), "NZD": ("New Zealand Dollars", "Cents", 100),
    "SAR": ("Saudi Riyals", "Halalas", 100), "QAR": ("Qatari Riyals", "Dirhams", 100), "JPY": ("Yen", None, 1),
    "CHF": ("Swiss Francs", "Centimes", 100), "ZAR": ("Rand", "Cents", 100), "MYR": ("Ringgit", "Sen", 100),
    "OMR": ("Omani Rials", "Baisa", 1000), "BHD": ("Bahraini Dinars", "Fils", 1000), "KWD": ("Kuwaiti Dinars", "Fils", 1000),
}


def _below_thousand(n: int) -> str:
    words = []
    if n >= 100:
        words.append(f"{_ONES[n // 100]} Hundred")
        n %= 100
    if n >= 20:
        words.append(_TENS[n // 10] + (f"-{_ONES[n % 10]}" if n % 10 else ""))
    elif n:
        words.append(_ONES[n])
    return " ".join(words)


def _integer_words(n: int, indian: bool) -> str:
    if n == 0:
        return "Zero"
    scales = ([(10**7, "Crore"), (10**5, "Lakh"), (1000, "Thousand")] if indian
              else [(10**9, "Billion"), (10**6, "Million"), (1000, "Thousand")])
    parts = []
    for size, name in scales:
        if n >= size:
            head = n // size
            parts.append(f"{_integer_words(head, indian) if head >= 1000 else _below_thousand(head)} {name}")
            n %= size
    if n:
        parts.append(_below_thousand(n))
    return " ".join(parts)


def amount_in_words(amount: float, currency: str) -> str:
    """'Rupees Eighty-Three Lakh ... and Fifty Paise Only' — the line printed under a quotation total."""
    major, minor, per = CURRENCY_WORDS.get(currency, (currency, None, 100))
    whole = int(amount)
    fraction = round((amount - whole) * per)
    if fraction >= per:
        whole, fraction = whole + 1, 0
    text = f"{major} {_integer_words(whole, currency == 'INR')}"
    if fraction:
        text += f" and {_integer_words(fraction, False)} {minor}" if minor else f" and {fraction}/{per}"
    return text + " Only"
