"""Checks for the rules parser on different receipt layouts. Run: .venv/bin/python test_rules.py

When a real receipt parses wrong, paste its OCR lines in here as a new case,
fix rules.py / lexicon.json until it passes, and keep it so it never regresses.
"""
from pathlib import Path

from remi_receipts.models import check_totals
from remi_receipts.rules import parse_receipt_rules


def items(r):
    return [(i.name, i.quantity, i.unit, i.total_price) for i in r.items]


def test_us_grocery():
    r = parse_receipt_rules([
        "FRESHWAY   MARKET", "123 MAIN   ST,   SPRINGFIELD", "10/27/2026   18:42",
        "BNLS   CHKN   BRST   9.98", "2 @ 4.99", "ORG   BANANAS   1.64", "0.82 kg @ 2.00/kg",
        "SRDGH BREAD   4.29", "COUPON   -1.00", "3 x GRK YOGURT   5.97",
        "SUBTOTAL   20.88", "TAX   0.72", "TOTAL   21.60", "VISA ****4821   21.60", "THANK YOU!",
    ])
    assert r.store_name == "Freshway Market"
    assert r.purchase_date == "2026-10-27" and r.purchase_time == "18:42"
    assert items(r) == [
        ("Boneless chicken breast", 2, "each", 9.98),
        ("Organic bananas", 0.82, "kg", 1.64),
        ("Sourdough bread", 1, "each", 3.29),
        ("Greek yogurt", 3, "each", 5.97),
    ]
    assert r.payment_method == "VISA ****4821"
    assert check_totals(r) == []


def test_european_layout():
    # Comma decimals, day-first dotted date, tax flag letters, € symbol, MwSt.
    r = parse_receipt_rules([
        "BIOMARKT KREUZBERG", "Oranienstr. 12", "10999 Berlin", "03.04.2026 09:15",
        "Vollmilch 1L   1,19 A", "Bio Bananen   2,49 A", "Kaffee 500g x2   9,98 B",
        "Pfand   -0,25", "SUMME EUR   13,41", "MwSt 7%   0,58", "Bar   15,00", "Rückgeld   1,59",
    ], default_currency="EUR")
    assert r.purchase_date == "2026-04-03"
    assert r.currency in ("EUR",)
    assert [(n, q, t) for n, q, _, t in items(r)] == [
        ("Vollmilch 1L", 1, 1.19), ("Bio bananen", 1, 2.49), ("Kaffee 500g", 2, 9.73),
    ]
    assert r.tax == 0.58


def test_price_on_next_line_and_ocr_noise():
    # Name and price on separate rows; "4.9O" has a letter O where a zero should be.
    r = parse_receipt_rules([
        "CORNER SHOP", "2026-01-05 7:30 PM",
        "CHOC CHPS COOKIES", "2 @ 2.45   4.9O",
        "SPKL WTR 12PK   5.99",
        "TP 24 ROLL   12.49", "SAVINGS   2.00-",
        "SUB TOTAL   21.38", "SALES TAX   1.20", "BALANCE DUE   22.58", "MASTERCARD XXXX1111",
    ])
    assert r.purchase_date == "2026-01-05" and r.purchase_time == "19:30"
    assert items(r) == [
        ("Chocolate chips cookies", 2, "each", 4.90),
        ("Sparkling water 12PK", 1, "each", 5.99),
        ("Toilet paper 24 roll", 1, "each", 10.49),
    ]
    assert r.total == 22.58 and r.payment_method == "MASTERCARD ****1111"
    assert check_totals(r) == []


def test_carrefour_tahiti_real_photo():
    # Real phone photo, OCR output saved from PaddleOCR. Whole-franc prices ("130F"),
    # barcode under every item, department headings, "kgX" weight line, TVA table.
    lines = (Path(__file__).parent / "samples" / "carrefour_tahiti.ocr.txt").read_text().splitlines()
    r = parse_receipt_rules(lines, date_order="DMY")
    assert r.store_name == "Carrefour" and r.currency == "XPF"
    assert len(r.items) == 16 and r.item_count_printed == 16
    assert r.total == 8604 and r.tax == 607 and r.payment_method == "CARD"
    assert sum(i.total_price for i in r.items) == 8604
    first, prune = r.items[0], r.items[10]
    assert (first.total_price, first.barcode, first.category) == (130, "3665676000975", "beverages")
    assert (prune.quantity, prune.unit, prune.unit_price, prune.total_price) == (0.12, "kg", 895, 107)
    assert [i.category for i in r.items].count("seafood") == 4
    assert check_totals(r) == [] and r.notes == []


def test_missing_item_is_flagged():
    r = parse_receipt_rules(["SHOP", "MLK   3.49", "SUBTOTAL   7.48", "TOTAL   7.48"])
    assert check_totals(r), "items don't reach the subtotal, so the scan should be flagged"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("PASS", name)
            except AssertionError as e:
                print("FAIL", name, e)
