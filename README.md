# Receipt scanner

Turns photos of shopping receipts into structured JSON: store, date, every product with quantity, unit, price, barcode and category, plus subtotal, tax, total and payment method. Runs fully offline. PaddleOCR reads the text, then hand-written rules interpret it. No API key needed.

## Use it

```sh
./run.sh
```

The first run creates the Python environment (a few minutes) and downloads the OCR models (~50 MB). After that it opens http://localhost:8765. Drop photos on the page. Each scan:

- shows the items, totals and any problems on the page,
- can be downloaded as JSON, or all scans together as one `receipts.json`,
- is saved automatically to `output/<photo name>.json`.

Scans marked **Check this one** failed a sanity check: the items don't add up to the subtotal or total, the item count doesn't match the printed article count, or some lines couldn't be read.

Command line, without the UI:

```sh
.venv/bin/python scan_receipt.py photo.jpg                  # JSON to stdout
.venv/bin/python scan_receipt.py photo.jpg --save remi.db   # also store in SQLite
.venv/bin/python scan_receipt.py photo.jpg --ocr-only       # raw OCR text, for debugging
```

## Files

| Path | What it does |
|---|---|
| `app.py`, `static/index.html` | The local web UI |
| `remi_receipts/ocr.py` | Photo → text lines (PaddleOCR mobile models) |
| `remi_receipts/rules.py` | Text lines → receipt (the parsing rules) |
| `remi_receipts/lexicon.json` | Abbreviations, product categories, store section headings. **Extend this as you scan new stores.** |
| `remi_receipts/models.py` | The JSON shape and the totals/count checks |
| `remi_receipts/store.py` | Optional SQLite storage |
| `remi_receipts/parse.py` | Optional Claude-based parser (`--parser claude`, needs `ANTHROPIC_API_KEY`) |
| `test_rules.py` | Real and synthetic receipts that must keep parsing correctly |

## When a receipt parses wrong

1. Run `scan_receipt.py photo.jpg --ocr-only > samples/name.ocr.txt` to save its OCR text.
2. Add a test in `test_rules.py` that loads it and asserts what should come out.
3. Adjust `rules.py` or `lexicon.json` until `.venv/bin/python test_rules.py` passes.
