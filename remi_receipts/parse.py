"""Step 2: OCR text lines -> structured receipt, using Claude.

Only the OCR *text* is sent (not the image), so each call is small and cheap.
"""
import os
from typing import Optional

import anthropic

from .models import Receipt, check_totals  # noqa: F401  (re-exported)

MODEL = os.environ.get("REMI_RECEIPT_MODEL", "claude-opus-5-5")


SYSTEM = """You convert OCR text from shopping receipts into structured data for a household inventory app.

The text comes from OCR, so expect misread characters (O/0, l/1, S/5), split lines, and noise.
Rules:
- One item per purchased product. If a quantity line like "2 @ 1.99" follows a product, merge it into that product.
- A line like "3 x MILK" or "MILK  QTY 3" means quantity 3.
- Weighted items ("0.82 kg @ 4.99/kg") use the weight as quantity and the kg/lb unit.
- Discount/coupon lines that follow an item reduce that item: put them in its discount and lower total_price.
- Do NOT make items out of subtotal, tax, total, change, payment, loyalty or store-info lines.
- Never invent products or prices. If something is unreadable, keep your best reading and add a note."""


def parse_receipt(lines: list[str], client: Optional[anthropic.Anthropic] = None) -> Receipt:
    client = client or anthropic.Anthropic()
    response = client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM,
        output_config={"effort": "low"},
        messages=[{"role": "user", "content": "Receipt OCR text:\n\n" + "\n".join(lines)}],
        output_format=Receipt,
    )
    if response.stop_reason == "refusal":
        raise RuntimeError(f"Model declined to parse this receipt: {response.stop_details}")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Receipt too long for one response; raise max_tokens")
    return response.parsed_output
