"""Step 2 (offline): OCR text lines -> structured receipt with hand-written rules.

No API key, no model download, runs in milliseconds. It covers the common
"PRODUCT ........ PRICE" layout plus quantity, weight and coupon lines.
Grow lexicon.json as you meet new stores; anything the rules can't place ends
up in `notes` so the app can ask the user to review.
"""
import json
import re
from pathlib import Path
from typing import Optional

from .models import Item, Receipt

_LEXICON = json.loads((Path(__file__).parent / "lexicon.json").read_text())
ABBREVIATIONS: dict[str, str] = _LEXICON["abbreviations"]
CATEGORIES: dict[str, list[str]] = _LEXICON["categories"]
DEPARTMENTS: dict[str, str] = {k: v for k, v in _LEXICON["departments"].items() if not k.startswith("_")}

# A money amount: "4.99", "$4.99", "4,99", "1.00-", and whole-unit currencies such
# as Pacific/CFA francs ("130F", "1 030 XPF") which only count with a currency mark.
_SUFFIX = r"(?:F|\s?(?:€|XPF|F\s?CFA|CFA|EUR))"
_AMOUNT = (
    rf"-?(?:[$€£¥₹]\s?)?\d{{1,7}}[.,]\d{{2}}{_SUFFIX}?-?"
    rf"|-?[$€£¥₹]\s?\d{{1,7}}-?"
    rf"|-?\d{{1,7}}{_SUFFIX}-?"
)
# "<body> <amount>" optionally followed by a tax flag such as "F", "T", "A", "*".
PRICED_LINE = re.compile(rf"^(?P<body>.*?)\s*(?P<amount>{_AMOUNT})(?:\s+[A-Z*]{{1,2}})?$")
BARCODE_LINE = re.compile(r"^\d{8,14}$")
ITEM_COUNT = re.compile(r"^(?P<n>\d{1,3})\s*(ARTICLES?|ARTICLE\(S\)|ART\.?|ITEMS?|ARTIKEL)\b|\b(ITEMS?\s+SOLD|ARTICLES?)\s*:?\s*(?P<n2>\d{1,3})\b", re.I)
# "2 @ 4.99", "2 x 4.99 ea", optionally with the line total at the end.
QTY_LINE = re.compile(rf"^(?P<qty>\d{{1,3}})\s*[@xX]\s*(?P<unit>{_AMOUNT})(?:\s*(?:ea|each|EA))?(?:\s+(?P<total>{_AMOUNT}))?$")
# "0.82 kg @ 2.00/kg", "1.5 lb @ $3.99 / lb", optionally with the line total.
WEIGHT_LINE = re.compile(
    rf"^(?P<qty>\d+[.,]\d+)\s*(?P<unit>kg|lbs?|g)\s*[@xX×]\s*(?P<price>{_AMOUNT})\s*/\s*(?:kg|lbs?|g)(?:\s+(?P<total>{_AMOUNT}))?$",
    re.I,
)
# Quantity written in the product line itself: "3 x GREEK YOGURT", "GREEK YOGURT x3", "QTY 3".
LEADING_QTY = re.compile(r"^(?P<qty>\d{1,3})\s*[xX*]\s+(?P<rest>.+)$")
TRAILING_QTY = re.compile(r"^(?P<rest>.+?)\s+(?:[xX]\s*|QTY\s*)(?P<qty>\d{1,3})$", re.I)

SUBTOTAL = re.compile(r"\b(SUB\s*-?\s*TOTAL|ZWISCHENSUMME|SOUS-TOTAL|SUBTOTALE)\b", re.I)
TAX = re.compile(r"\b(SALES\s+)?(TAX|VAT|GST|HST|PST|MWST|TVA|IVA)\b", re.I)
TOTAL = re.compile(r"\b(TOTAL|BALANCE\s+DUE|AMOUNT\s+DUE|GRAND\s+TOTAL|SUMME|TOTAAL|TOTALE|MONTANT|GESAMT)\b", re.I)
PAYMENT = re.compile(r"^(VISA|MASTERCARD|MASTER\s*CARD|AMEX|AMERICAN\s+EXPRESS|DISCOVER|DEBIT|CREDIT|CASH|EBT|APPLE\s*PAY|GOOGLE\s*PAY|BAR|KARTE|EC|CARTE|ESP[EÈ]CES|EFECTIVO|TARJETA|CONTANTI)\b", re.I)
DISCOUNT = re.compile(r"\b(COUPON|DISCOUNT|SAVINGS?|PROMO|MARKDOWN|DEAL|REWARD|OFF)\b", re.I)
SKIP = re.compile(
    r"\b(CHANGE|R[UÜ]CKGELD|WECHSELGELD|RENDU|CAMBIO|VUELTO|TENDER(ED)?|THANK|CASHIER|REGISTER|TRANS(ACTION)?|ITEMS?\s+SOLD|POINTS|MEMBER|APPROVED|AUTH|"
    r"REF(ERENCE)?|TERMINAL|RECEIPT|WWW\.|HTTP|SURVEY|RETURN|POLICY|TEL|PHONE)\b",
    re.I,
)
DATE_ISO = re.compile(r"\b(?P<y>\d{4})[-/.](?P<m>\d{1,2})[-/.](?P<d>\d{1,2})\b")
DATE_NUM = re.compile(r"\b(?P<a>\d{1,2})(?P<sep>[-/.])(?P<b>\d{1,2})(?P=sep)(?P<y>\d{2}|\d{4})\b")
TIME = re.compile(r"\b(?P<h>\d{1,2}):(?P<m>\d{2})(?::\d{2})?\s*(?P<ampm>[AaPp][Mm])?\b")
ADDRESS = re.compile(
    r"^\d+\s+\w+.*\b(ST|STREET|AVE|AVENUE|RD|ROAD|BLVD|DR|DRIVE|LN|LANE|WAY|HWY|PL|CT|PKWY)\b|\b[A-Z]{2}\s+\d{5}\b|\d{5}(-\d{4})?$"
    r"|(STR\.|STRASSE|STRAßE|WEG|PLATZ|GASSE|RUE|VIA|CALLE)\s*\d+|^\d{4,5}\s+[A-Za-zÀ-ÿ]"
    r"|\bBP\s*\d+|\bPLAZA\b|\bMALL\b|CENTRE\s*COMMERCIAL|\d{5}\s*[A-Z]{3,}",
    re.I,
)
CARD_DIGITS = re.compile(r"[*Xx#]{2,}\s*(\d{4})")
CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY", "₹": "INR"}
PAYMENT_KINDS = {"BAR": "CASH", "ESPECES": "CASH", "ESPÈCES": "CASH", "EFECTIVO": "CASH", "CONTANTI": "CASH",
                 "CARTE": "CARD", "KARTE": "CARD", "EC": "CARD", "TARJETA": "CARD"}
PACIFIC_FRANC_PLACES = re.compile(r"PAPEETE|TAHITI|POLYN[EÉ]SIE|NOUM[EÉ]A|CAL[EÉ]DONIE|WALLIS|\bXPF\b", re.I)


def parse_receipt_rules(lines: list[str], default_currency: str = "USD", date_order: str = "MDY") -> Receipt:
    """date_order breaks ties for dates like 03/04/2026: "MDY" (US) or "DMY" (most other countries)."""
    lines = [ln.strip() for ln in lines if ln.strip()]
    text = "\n".join(lines)

    items: list[Item] = []
    notes: list[str] = []
    subtotal = tax = total = None
    payment_method: Optional[str] = None
    header: list[str] = []
    pending_name: Optional[str] = None  # a product name whose price is on the next line
    department: Optional[str] = None  # current section heading ("BOISSONS", "PRODUCE", ...)
    tax_parts: list[float] = []  # per-rate rows of a tax table
    tax_table_total: Optional[float] = None
    item_count: Optional[int] = None
    section = "header"  # header -> items -> totals

    for line in lines:
        line = _fix_amount_tokens(line)
        priced = PRICED_LINE.match(line)
        amount = _money(priced.group("amount")) if priced else None

        if BARCODE_LINE.match(line):
            if items and items[-1].barcode is None:
                items[-1].barcode = line
            continue
        if m := ITEM_COUNT.search(line):
            item_count = int(m.group("n") or m.group("n2"))
            continue

        # --- totals & payment block -------------------------------------
        if SUBTOTAL.search(line):
            subtotal = amount if amount is not None else subtotal
            section = "totals"
            continue
        if TAX.search(line):
            if amount is not None:
                tax = round((tax or 0) + amount, 2)
            else:
                # Tax table row "TVA 5%  5%  6113  306  6419": columns are net, tax, gross.
                numbers = [_number(n) for n in re.findall(r"(?<![\d.,])(\d+(?:[.,]\d+)?)(?![\d.,]|\s*%)", line)]
                if len(numbers) >= 3:
                    if re.match(r"^\s*TOTAL", line, re.I):
                        tax_table_total = numbers[-2]
                    else:
                        tax_parts.append(numbers[-2])
            section = "totals"
            continue
        if TOTAL.search(line):
            if total is None:
                total = amount
            section = "totals"
            continue
        if PAYMENT.search(line):
            if payment_method is None:
                card = CARD_DIGITS.search(line)
                kind = PAYMENT.search(line).group(1).upper()
                kind = PAYMENT_KINDS.get(kind, kind)
                payment_method = f"{kind} ****{card.group(1)}" if card else kind
            if section != "header":
                section = "totals"
            continue
        if section == "totals" or SKIP.search(line):
            continue

        # --- modifiers that belong to the previous product --------------
        qty_match = QTY_LINE.match(line)
        weight_match = WEIGHT_LINE.match(line)
        if qty_match or weight_match:
            m = qty_match or weight_match
            qty = _number(m.group("qty"))
            unit = "each" if qty_match else m.group("unit").lower().rstrip("s")
            unit_price = _money(m.group("unit") if qty_match else m.group("price"))
            line_total = _money(m.group("total")) if m.group("total") else round(qty * unit_price, 2)
            if not pending_name and not items and len(header) > 1 and _looks_like_product(header[-1]):
                pending_name = header.pop()  # product printed before any priced line
            if pending_name:
                items.append(_make_item(pending_name, qty, unit, unit_price, line_total, f"{pending_name}\n{line}", department))
                pending_name = None
            elif items:
                prev = items[-1]
                prev.quantity, prev.unit, prev.unit_price = qty, unit, unit_price
                prev.raw_text += "\n" + line
                if abs(prev.total_price - line_total) > max(0.02, 0.01 * abs(line_total)):
                    notes.append(f"'{prev.name}': {qty:g} x {unit_price:.2f} = {line_total:.2f}, but line shows {prev.total_price:.2f}")
            section = "items"
            continue

        if priced and DISCOUNT.search(line) or (amount is not None and amount < 0):
            if items:
                prev = items[-1]
                prev.discount = round(prev.discount + abs(amount), 2)
                prev.total_price = round(prev.total_price - abs(amount), 2)
                prev.raw_text += "\n" + line
            else:
                notes.append(f"Discount with no product before it: '{line}'")
            continue

        # --- ordinary product line --------------------------------------
        if priced and _looks_like_product(priced.group("body")):
            body = priced.group("body").strip(" .:-")
            if pending_name:
                if _looks_like_heading(pending_name):
                    department = pending_name  # an unknown section heading, not a product
                else:
                    notes.append(f"No price found for '{pending_name}'")
                pending_name = None
            qty = 1.0
            if m := LEADING_QTY.match(body):
                qty, body = float(m.group("qty")), m.group("rest")
            elif m := TRAILING_QTY.match(body):
                qty, body = float(m.group("qty")), m.group("rest")
            unit_price = round(amount / qty, 2) if qty != 1 else amount
            items.append(_make_item(body, qty, "each", unit_price, amount, line, department))
            section = "items"
            continue

        # --- unpriced text ----------------------------------------------
        if _known_department(line):
            department = line
            section = "items"
        elif section == "header":
            header.append(line)
        elif _looks_like_product(line):
            if pending_name:
                notes.append(f"No price found for '{pending_name}'")
            pending_name = line
        else:
            notes.append(f"Couldn't read line: '{line}'")

    if pending_name:
        notes.append(f"No price found for '{pending_name}'")

    if tax_table_total is not None:
        tax = tax_table_total
    elif tax_parts and tax is None:
        tax = round(sum(tax_parts), 2)

    store_name, store_address = _store_info(header)
    return Receipt(
        store_name=store_name,
        store_address=store_address,
        purchase_date=_find_date(text, date_order),
        purchase_time=_find_time(text),
        currency=_find_currency(text, default_currency),
        item_count_printed=item_count,
        items=items,
        subtotal=subtotal,
        tax=tax,
        total=total,
        payment_method=payment_method,
        notes=notes,
    )


def expand_name(raw: str) -> str:
    words = []
    for token in raw.split():
        key = token.upper().strip(".,:;")
        words.append(ABBREVIATIONS.get(key, token if any(c.isdigit() for c in token) else token.lower()))
    name = " ".join(words)
    return name[:1].upper() + name[1:]


def categorize(name: str) -> str:
    # Keywords match at the start of a word ("oil" must not hit "toilet"), and the
    # longest match wins ("toilet" beats "roll" in "toilet paper 24 roll").
    lowered = name.lower()
    best = (0, "other")
    for category, keywords in CATEGORIES.items():
        for k in keywords:
            if len(k) > best[0] and re.search(r"(?<![a-zà-ÿ])" + re.escape(k), lowered):
                best = (len(k), category)
    return best[1]


def _make_item(raw_name: str, qty: float, unit: str, unit_price: Optional[float], total: float, raw_text: str,
               department: Optional[str] = None) -> Item:
    name = expand_name(raw_name)
    # The store's own section heading beats guessing from the product name.
    category = _known_department(department) if department else None
    return Item(raw_text=raw_text, name=name, category=category or categorize(name), quantity=qty, unit=unit,
                unit_price=unit_price, total_price=total, discount=0.0, department=department)


def _known_department(line: str) -> Optional[str]:
    key = re.sub(r"[^A-ZÀ-Ü]", "", line.upper())
    if not key:
        return None
    for heading, category in DEPARTMENTS.items():
        if key.startswith(heading):
            return category
    return None


def _looks_like_heading(text: str) -> bool:
    return text.isupper() and not any(c.isdigit() for c in text)


def _looks_like_product(text: str) -> bool:
    letters = sum(c.isalpha() for c in text)
    return letters >= 2 and not DATE_NUM.search(text) and not TIME.search(text)


def _fix_ocr_digits(s: str) -> str:
    # Inside amounts, OCR commonly confuses these letters with digits.
    return s.translate(str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1", "S": "5", "B": "8"}))


_AMOUNT_LIKE = re.compile(r"^-?[$€£]?[\dOolISB]{1,7}(?:[.,][\dOolISB]{2}F?|F)-?$")


def _fix_amount_tokens(line: str) -> str:
    """Turn "4.9O" into "4.90" without touching words like "SOS" or "BOIL"."""
    return " ".join(
        _fix_ocr_digits(t) if _AMOUNT_LIKE.match(t) and any(c.isdigit() for c in t) else t
        for t in line.split(" ")
    )


def _money(s: str) -> float:
    s = s.replace(" ", "")
    negative = s.startswith("-") or s.endswith("-")
    s = re.sub(r"(F\s?CFA|XPF|CFA|EUR|€|F)$", "", s.strip("-")).strip("-").lstrip("$€£¥₹").replace(",", ".")
    value = float(s)
    return -value if negative else value


def _number(s: str) -> float:
    return float(s.replace(",", "."))


def _store_info(header: list[str]) -> tuple[Optional[str], Optional[str]]:
    name = None
    address = []
    for line in header:
        if DATE_NUM.search(line) or DATE_ISO.search(line) or TIME.search(line):
            continue
        if ADDRESS.search(line):
            address.append(line)
        elif name is None and _looks_like_product(line):
            name = " ".join(line.split()).title()
    return name, ", ".join(" ".join(a.split()) for a in address) or None


def _find_date(text: str, date_order: str) -> Optional[str]:
    if m := DATE_ISO.search(text):
        y, mo, d = int(m["y"]), int(m["m"]), int(m["d"])
    elif m := DATE_NUM.search(text):
        a, b, y = int(m["a"]), int(m["b"]), int(m["y"])
        y += 2000 if y < 100 else 0
        day_first = date_order == "DMY" or m["sep"] == "." or a > 12
        if b > 12:
            day_first = False
        d, mo = (a, b) if day_first else (b, a)
    else:
        return None
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return None
    return f"{y:04d}-{mo:02d}-{d:02d}"


def _find_time(text: str) -> Optional[str]:
    m = TIME.search(text)
    if not m:
        return None
    h, mi = int(m["h"]), int(m["m"])
    if m["ampm"]:
        h = h % 12 + (12 if m["ampm"].lower() == "pm" else 0)
    return f"{h:02d}:{mi:02d}" if h < 24 and mi < 60 else None


def _find_currency(text: str, default: str) -> str:
    if re.search(r"\d\s?F\s?CFA\b|\bFCFA\b", text):
        return "XOF"
    if re.search(r"\d+F\b", text) and PACIFIC_FRANC_PLACES.search(text):
        return "XPF"
    for symbol, code in CURRENCY_SYMBOLS.items():
        if symbol in text:
            return code
    if m := re.search(r"\b(USD|EUR|GBP|CAD|AUD|CHF|JPY|INR|NGN|ZAR|KES|GHS)\b", text):
        return m.group(1)
    return default
