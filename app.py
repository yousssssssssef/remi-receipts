"""Local web UI: drop receipt photos in, get JSON files out.

    ./run.sh            (or: .venv/bin/python app.py)
    then open http://localhost:8765

Every scan is also written to output/<photo name>.json.
Runs fully offline (PaddleOCR + rules parser); nothing leaves this machine.
"""
import io
import json
import re
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from PIL import Image, ImageOps

from remi_receipts.models import check_totals
from remi_receipts.ocr import ocr_lines
from remi_receipts.rules import parse_receipt_rules

try:  # iPhone photos are HEIC
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:
    pass

ROOT = Path(__file__).parent
OUTPUT = ROOT / "output"
INDEX_HTML = ROOT / "static" / "index.html"
PORT = 8765
MAX_UPLOAD = 30 * 1024 * 1024
OCR_LOCK = threading.Lock()  # the OCR engine isn't thread-safe; scan one photo at a time


def scan_image(data: bytes, currency: str, date_order: str) -> dict:
    # Normalise to an upright JPEG: phones store rotation in EXIF, and OCR needs it applied.
    image = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    with tempfile.NamedTemporaryFile(suffix=".jpg") as tmp:
        image.save(tmp.name, quality=95)
        with OCR_LOCK:
            lines = ocr_lines(tmp.name)
    receipt = parse_receipt_rules(lines, default_currency=currency, date_order=date_order)
    warnings = check_totals(receipt)
    return {
        "receipt": receipt.model_dump(),
        "warnings": warnings,
        "needs_review": bool(warnings or receipt.notes),
        "ocr_text": lines,
    }


def safe_stem(filename: str) -> str:
    stem = Path(filename).stem or "receipt"
    return re.sub(r"[^\w.-]+", "_", stem)[:80]


def unique_path(stem: str) -> Path:
    path = OUTPUT / f"{stem}.json"
    n = 2
    while path.exists():
        path = OUTPUT / f"{stem}_{n}.json"
        n += 1
    return path


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, INDEX_HTML.read_bytes(), "text/html; charset=utf-8")
        else:
            self._send(404, b"Not found", "text/plain")

    def do_POST(self):
        url = urlparse(self.path)
        if url.path != "/scan":
            return self._send(404, b"Not found", "text/plain")
        length = int(self.headers.get("Content-Length") or 0)
        if not 0 < length <= MAX_UPLOAD:
            return self._json(400, {"error": "Empty upload or file larger than 30 MB"})
        params = parse_qs(url.query)
        filename = params.get("filename", ["receipt"])[0]
        currency = params.get("currency", ["USD"])[0].upper()[:3]
        date_order = "DMY" if params.get("date_order", ["MDY"])[0] == "DMY" else "MDY"
        data = self.rfile.read(length)
        try:
            result = scan_image(data, currency, date_order)
        except Exception as e:  # report bad images to the page instead of dropping the connection
            return self._json(422, {"error": f"Could not scan {filename}: {e}"})
        OUTPUT.mkdir(exist_ok=True)
        out_path = unique_path(safe_stem(filename))
        result = {"source_file": filename, **result}
        out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
        self._json(200, {**result, "saved_as": str(out_path.relative_to(ROOT))})

    def _json(self, status: int, payload: dict):
        self._send(status, json.dumps(payload, ensure_ascii=False).encode(), "application/json")

    def _send(self, status: int, body: bytes, content_type: str):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        sys.stderr.write("%s\n" % (fmt % args))


if __name__ == "__main__":
    print("Loading OCR models (first run downloads ~50 MB)...", file=sys.stderr)
    from remi_receipts.ocr import _engine

    _engine()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Receipt scanner running at http://localhost:{PORT}  (Ctrl+C to stop)", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
