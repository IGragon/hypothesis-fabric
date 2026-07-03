from __future__ import annotations

import os


def parse_pdf(path: str) -> list[dict]:
    import fitz

    doc = fitz.open(path)
    doc_id = os.path.splitext(os.path.basename(path))[0]
    results: list[dict] = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text()
        if not text.strip():
            continue
        results.append({
            "text": text,
            "meta": {
                "page": page_num + 1,
                "path": path,
                "doc_id": doc_id,
            },
        })
    doc.close()
    return results
