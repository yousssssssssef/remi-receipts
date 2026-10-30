"""Scan a receipt photo: PaddleOCR -> parser -> JSON (and optionally SQLite).

    python scan_receipt.py receipt.jpg                    # offline rules parser
    python scan_receipt.py receipt.jpg --save remi.db     # also store it
    python scan_receipt.py receipt.jpg --date-order DMY   # 03/04 means 3 April
    python scan_receipt.py receipt.jpg --parser claude    # Claude API (needs ANTHROPIC_API_KEY)
    python scan_receipt.py receipt.jpg --ocr-only         # just the OCR text
"""
import argparse
import json
import sys

from remi_receipts.ocr import ocr_lines


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--save", metavar="DB", help="SQLite file to store the receipt in")
    ap.add_argument("--parser", choices=["rules", "claude"], default="rules")
    ap.add_argument("--currency", default="USD", help="Used when the receipt shows no currency symbol")
    ap.add_argument("--date-order", choices=["MDY", "DMY"], default="MDY")
    ap.add_argument("--ocr-only", action="store_true", help="Print OCR lines and stop")
    args = ap.parse_args()

    lines = ocr_lines(args.image)
    print("--- OCR text ---", file=sys.stderr)
    print("\n".join(lines), file=sys.stderr)
    if args.ocr_only:
        return 0

    from remi_receipts.models import check_totals

    if args.parser == "claude":
        from remi_receipts.parse import parse_receipt

        receipt = parse_receipt(lines)
    else:
        from remi_receipts.rules import parse_receipt_rules

        receipt = parse_receipt_rules(lines, default_currency=args.currency, date_order=args.date_order)
    warnings = check_totals(receipt)
    print(json.dumps({"receipt": receipt.model_dump(), "warnings": warnings}, indent=2))

    if args.save:
        from remi_receipts.store import save_receipt

        receipt_id = save_receipt(args.save, receipt, warnings, lines)
        print(f"Saved as receipt #{receipt_id} in {args.save}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
