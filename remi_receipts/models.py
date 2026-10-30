"""The receipt shape every parser produces and the store saves."""
from typing import Optional

from pydantic import BaseModel, Field


class Item(BaseModel):
    raw_text: str = Field(description="The receipt line(s) this item came from, verbatim")
    name: str = Field(description="Readable product name, abbreviations expanded (e.g. 'BNLS CHKN BRST' -> 'Boneless chicken breast')")
    category: str = Field(description="One of: produce, meat, seafood, dairy, bakery, frozen, pantry, beverages, snacks, household, personal care, other")
    quantity: float = Field(description="Count of units, or weight if sold by weight")
    unit: str = Field(description="'each', 'kg', 'lb', 'g', 'l', etc.")
    unit_price: Optional[float]
    total_price: float = Field(description="Line total after any line-level discount")
    discount: float = Field(description="Discount applied to this line, as a positive number; 0 if none")
    barcode: Optional[str] = Field(default=None, description="EAN/UPC printed under the item, if any")
    department: Optional[str] = Field(default=None, description="Store section heading the item was listed under, if any")


class Receipt(BaseModel):
    store_name: Optional[str]
    store_address: Optional[str]
    purchase_date: Optional[str] = Field(description="ISO 8601 date, YYYY-MM-DD")
    purchase_time: Optional[str] = Field(description="24h HH:MM")
    currency: str = Field(description="ISO 4217 code, guessed from symbols/location if not printed")
    items: list[Item]
    subtotal: Optional[float]
    tax: Optional[float]
    total: Optional[float]
    payment_method: Optional[str] = Field(description="e.g. 'VISA ****1234', 'cash'; never more than the last 4 card digits")
    item_count_printed: Optional[int] = Field(default=None, description="Article count printed on the receipt, e.g. '16 Article(s)'")
    notes: list[str] = Field(description="Anything unreadable or ambiguous the user should double-check")


def check_totals(receipt: Receipt, tolerance: float = 0.02) -> list[str]:
    """Cheap sanity checks so the app can ask the user to review a scan."""
    warnings = []
    items_sum = round(sum(i.total_price for i in receipt.items), 2)
    if receipt.subtotal is not None and abs(items_sum - receipt.subtotal) > tolerance:
        warnings.append(f"Items add up to {items_sum:.2f} but subtotal is {receipt.subtotal:.2f}; an item may be missing or misread")
    if receipt.subtotal is None and receipt.total is not None and receipt.items:
        # No subtotal printed: items should match the total, either tax-inclusive or tax-exclusive.
        candidates = [receipt.total] + ([receipt.total - receipt.tax] if receipt.tax else [])
        if all(abs(items_sum - c) > tolerance for c in candidates):
            warnings.append(f"Items add up to {items_sum:.2f} but total is {receipt.total:.2f}; an item may be missing or misread")
    if receipt.item_count_printed is not None:
        counted = sum(i.quantity if i.unit == "each" else 1 for i in receipt.items)
        if counted != receipt.item_count_printed:
            warnings.append(f"Receipt says {receipt.item_count_printed} articles but {counted:g} were read")
    if None not in (receipt.subtotal, receipt.tax, receipt.total):
        expected = round(receipt.subtotal + receipt.tax, 2)
        if abs(expected - receipt.total) > tolerance:
            warnings.append(f"Subtotal + tax = {expected:.2f} but total is {receipt.total:.2f}")
    if not receipt.items:
        warnings.append("No items found")
    return warnings
