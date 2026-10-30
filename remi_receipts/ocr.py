"""Step 1: receipt image -> text lines, using PaddleOCR (runs locally, CPU is fine)."""
from functools import lru_cache


@lru_cache(maxsize=1)
def _engine():
    from paddleocr import PaddleOCR

    # Mobile models are the lightweight PP-OCRv5 variants (~10 MB each).
    # Receipts are photographed upright, so skip the orientation/unwarp models.
    return PaddleOCR(
        text_detection_model_name="PP-OCRv5_mobile_det",
        text_recognition_model_name="PP-OCRv5_mobile_rec",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )


def ocr_lines(image_path: str, min_score: float = 0.5) -> list[str]:
    """Return the receipt's text as visual lines, top to bottom.

    PaddleOCR returns separate boxes for "MILK 2%" and "3.49" even when they sit
    on the same printed row, so boxes are regrouped into rows by vertical position.
    That keeps each product next to its price, which the parser relies on.
    """
    result = _engine().predict(image_path)[0]
    boxes = []
    for text, score, poly in zip(result["rec_texts"], result["rec_scores"], result["rec_polys"]):
        if score < min_score or not text.strip():
            continue
        ys = [p[1] for p in poly]
        xs = [p[0] for p in poly]
        boxes.append({"text": text.strip(), "top": min(ys), "bottom": max(ys), "left": min(xs)})

    boxes.sort(key=lambda b: (b["top"] + b["bottom"]) / 2)
    rows: list[list[dict]] = []
    for box in boxes:
        center = (box["top"] + box["bottom"]) / 2
        if rows:
            last = rows[-1]
            row_top = min(b["top"] for b in last)
            row_bottom = max(b["bottom"] for b in last)
            if row_top <= center <= row_bottom:
                last.append(box)
                continue
        rows.append([box])

    return ["   ".join(b["text"] for b in sorted(row, key=lambda b: b["left"])) for row in rows]
