from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pymupdf

from core.config import OCR_ENABLED, PAGE_IMAGE_DIR, RENDER_PAGE_IMAGES, EXPECTED_MOCK_QUESTIONS
from core.database import utcnow

# Handles common Allen/NEET forms: 1. / 1) / Q.1 / Question 1: / Q.No. 1
QUESTION_START = re.compile(
    # The question number may share a line with the stem or appear alone on a line.
    r"^\s*(?:Q(?:uestion)?\s*\.?\s*(?:No\.?\s*)?)?(\d{1,3})\s*[\.:)\-](?:\s+.*)?$",
    re.IGNORECASE,
)
QUESTION_START_ALT = re.compile(r"^\s*\((\d{1,3})\)(?:\s+.*)?$")
QUESTION_START_PREFIX_ONLY = re.compile(
    r"^\s*Q(?:uestion)?\s*\.?\s*(?:No\.?\s*)?(\d{1,3})\.?\s*$",
    re.IGNORECASE,
)
OPTION_START = re.compile(r"^\s*(?:\(([A-Da-d])\)|([A-Da-d])[\).])\s*(.*)$")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_line(line: str) -> str:
    line = line.replace("\u00a0", " ").replace("\u200b", "")
    line = re.sub(r"[ \t]+", " ", line)
    return line.strip()


def classify_subject(question_number: int) -> str | None:
    if 1 <= question_number <= 45:
        return "Physics"
    if 46 <= question_number <= 90:
        return "Chemistry"
    if 91 <= question_number <= 180:
        return "Biology"
    return None


def parse_test_number(filename: str, fallback: int) -> int:
    stem = Path(filename).stem
    patterns = [
        r"(?:test|mock|paper|major|minor|ft|part)[\s_-]*0*(\d{1,2})\b",
        r"\bT[\s_-]*0*(\d{1,2})\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, stem, re.IGNORECASE)
        if m:
            return int(m.group(1))
    return fallback


def infer_doc_kind(filename: str, forced_kind: str | None = None) -> str:
    if forced_kind:
        return forced_kind
    name = Path(filename).stem.lower()
    if any(word in name for word in ("solution", "soln", "answer", "anskey", "answerkey", "key")):
        return "solution"
    return "mock"


def _extract_layout_aware_text(page: Any) -> str:
    """Read one-column pages normally and two-column pages by column where detectable."""
    try:
        blocks = [b for b in page.get_text("blocks") if len(b) >= 5 and isinstance(b[4], str) and b[4].strip()]
        width = float(page.rect.width)
        left = [b for b in blocks if float(b[0]) < width * 0.49 and (float(b[2]) - float(b[0])) < width * 0.78]
        right = [b for b in blocks if float(b[0]) >= width * 0.49 and (float(b[2]) - float(b[0])) < width * 0.78]
        # Only switch to column-major extraction when both columns are populated clearly.
        if len(left) >= 3 and len(right) >= 3:
            full = [b for b in blocks if (float(b[2]) - float(b[0])) >= width * 0.78]
            left.sort(key=lambda b: (float(b[1]), float(b[0])))
            right.sort(key=lambda b: (float(b[1]), float(b[0])))
            full.sort(key=lambda b: (float(b[1]), float(b[0])))
            top_full = [b for b in full if float(b[1]) < min(float(x[1]) for x in left + right)]
            bottom_full = [b for b in full if float(b[1]) >= min(float(x[1]) for x in left + right)]
            ordered = top_full + left + right + bottom_full
            return "\n".join(str(b[4]).strip() for b in ordered if str(b[4]).strip())
    except Exception:
        pass
    return page.get_text("text", sort=True) or ""


def extract_pdf_pages(path: Path, save_images: bool = True) -> tuple[list[dict[str, Any]], list[str]]:
    """Extract page text; OCR low-text pages when PyMuPDF's OCR support is installed."""
    pages: list[dict[str, Any]] = []
    warnings: list[str] = []
    doc = pymupdf.open(path)
    paper_hash = sha256_file(path)[:16]
    try:
        for page_index, page in enumerate(doc):
            text = _extract_layout_aware_text(page)
            ocr_used = False
            if OCR_ENABLED and len(re.sub(r"\s", "", text)) < 35:
                try:
                    textpage = page.get_textpage_ocr(language="eng", dpi=250, full=True)
                    ocr_text = page.get_text("text", textpage=textpage, sort=True) or ""
                    if len(ocr_text.strip()) > len(text.strip()):
                        text = ocr_text
                        ocr_used = True
                except Exception as exc:
                    warnings.append(f"Page {page_index + 1}: OCR unavailable/failed ({type(exc).__name__}). Install Tesseract or RapidOCR if this is a scanned PDF.")
            image_path = None
            if save_images and RENDER_PAGE_IMAGES:
                try:
                    page_dir = PAGE_IMAGE_DIR / paper_hash
                    page_dir.mkdir(parents=True, exist_ok=True)
                    img = page_dir / f"page_{page_index + 1:03d}.jpg"
                    if not img.exists():
                        pix = page.get_pixmap(dpi=115, alpha=False)
                        pix.save(img)
                    image_path = str(img)
                except Exception as exc:
                    warnings.append(f"Page {page_index + 1}: could not render preview ({type(exc).__name__}).")
            pages.append({"page_number": page_index + 1, "text": text, "image_path": image_path, "ocr_used": ocr_used})
    finally:
        doc.close()
    return pages, warnings


def _is_question_start(line: str) -> tuple[bool, int | None]:
    for pattern in (QUESTION_START, QUESTION_START_ALT, QUESTION_START_PREFIX_ONLY):
        m = pattern.match(line)
        if m:
            n = int(m.group(1))
            if 1 <= n <= 250:
                return True, n
    return False, None


def _strip_question_marker(line: str) -> str:
    for pattern in (QUESTION_START, QUESTION_START_ALT, QUESTION_START_PREFIX_ONLY):
        if pattern.match(line):
            return pattern.sub("", line, count=1).strip()
    return line


def split_questions(pages: list[dict[str, Any]], paper_id: str, kind: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Split extracted pages into per-question records while retaining source page references.

    Parser is deliberately conservative. Any unusual layout is surfaced as a warning for review,
    instead of silently claiming that all questions were captured.
    """
    lines: list[tuple[int, str, str | None]] = []
    for page in pages:
        for raw in (page.get("text") or "").splitlines():
            line = normalize_line(raw)
            if line:
                lines.append((int(page["page_number"]), line, page.get("image_path")))
        # page boundary marker is handled as an empty line in accumulated question text implicitly
    starts: list[tuple[int, int, int]] = []
    for idx, (page_no, line, _) in enumerate(lines):
        ok, num = _is_question_start(line)
        if ok and num is not None:
            starts.append((idx, num, page_no))

    warnings: list[str] = []
    if not starts:
        return [], ["No question-number markers were detected. The PDF may be scanned, use a non-standard layout, or have questions split across columns."]

    # Reject obvious false positives such as numbered headings by preferring a long, plausible sequence.
    counts: dict[int, int] = {}
    for _, n, _ in starts:
        counts[n] = counts.get(n, 0) + 1
    if len(starts) < 10:
        warnings.append(f"Only {len(starts)} possible question starts found; review extraction before analysis.")

    questions: list[dict[str, Any]] = []
    for pos, (start_idx, qno, page_no) in enumerate(starts):
        ordinal = pos + 1
        end_idx = starts[pos + 1][0] if pos + 1 < len(starts) else len(lines)
        chunk_lines = lines[start_idx:end_idx]
        raw_text = "\n".join(item[1] for item in chunk_lines).strip()
        if len(raw_text) < 15:
            warnings.append(f"Question {qno}: very short extraction; possible parsing failure.")
            continue
        # Remove the question number prefix from the stored question body, retaining original Q number separately.
        first = chunk_lines[0][1]
        body_first = _strip_question_marker(first)
        body = "\n".join(([body_first] if body_first else []) + [x[1] for x in chunk_lines[1:]]).strip()
        options: dict[str, str] = {}
        for line in body.splitlines():
            om = OPTION_START.match(line)
            if om:
                letter = (om.group(1) or om.group(2)).upper()
                options[letter] = om.group(3).strip()
        confidence = 0.88
        if not options:
            confidence -= 0.12
        if len(body) < 35:
            confidence -= 0.2
        if len(body) > 6000:
            confidence -= 0.15
        questions.append({
            "id": f"{paper_id}:{kind}:{ordinal}:q{qno}",
            "kind": kind,
            "question_number": qno,
            "question_ordinal": ordinal,
            "subject": classify_subject(ordinal),
            "page_number": page_no,
            "question_text": body,
            "options": options,
            "page_image": next((x[2] for x in chunk_lines if x[2]), None),
            "analysis": None,
            "extraction_confidence": max(0.15, min(0.99, confidence)),
            "created_at": utcnow(),
        })

    # Duplicate numbers are common in sectioned test PDFs; retain them but flag for manual review.
    duplicates = [n for n, count in counts.items() if count > 1]
    if duplicates:
        warnings.append("Duplicate question-number markers detected: " + ", ".join(map(str, sorted(duplicates)[:30])) + ". Verify section numbering.")
    qnos = [q["question_number"] for q in questions]
    if kind in {"mock", "neet"} and len(questions) < 30:
        warnings.append(f"Only {len(questions)} questions were segmented. Check OCR/layout; do not treat this as a complete paper.")
    if kind == "mock" and len(questions) != EXPECTED_MOCK_QUESTIONS:
        warnings.append(f"Expected about {EXPECTED_MOCK_QUESTIONS} questions, extracted {len(questions)}. This paper needs review before matching.")
    if qnos and len(set(qnos)) < len(qnos):
        warnings.append("Some questions share the same number; the parser has kept all extracted segments.")
    return questions, warnings


def ingest_pdf(path: Path, kind: str, fallback_test_number: int = 1) -> dict[str, Any]:
    paper_hash = sha256_file(path)
    paper_id = paper_hash[:16]
    pages, warnings = extract_pdf_pages(path)
    label = Path(path).stem
    test_number = parse_test_number(path.name, fallback_test_number) if kind in {"mock", "solution"} else None
    full_text = "\n\n".join(f"[PAGE {p['page_number']}]\n{p['text']}" for p in pages)
    if kind in {"mock", "neet", "solution"}:
        questions, split_warnings = split_questions(pages, paper_id, kind)
        warnings.extend(split_warnings)
    else:
        questions = []
    return {
        "paper": {
            "id": paper_id,
            "kind": kind,
            "filename": path.name,
            "label": label,
            "test_number": test_number,
            "page_count": len(pages),
            "question_count": len(questions),
            "sha256": paper_hash,
            "status": "needs_review" if warnings else "extracted",
            "warnings_json": json.dumps(warnings, ensure_ascii=False),
            "created_at": utcnow(),
        },
        "questions": questions,
        "warnings": warnings,
        "full_text": full_text,
    }


def save_uploaded_file(uploaded_file, target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9._() -]", "_", uploaded_file.name).strip() or "uploaded.pdf"
    target = target_dir / safe_name
    payload = uploaded_file.getbuffer()
    if target.exists():
        incoming_hash = hashlib.sha256(bytes(payload)).hexdigest()[:8]
        target = target_dir / f"{target.stem}_{incoming_hash}{target.suffix}"
    target.write_bytes(payload)
    return target


def folder_pdfs(folder: Path) -> list[Path]:
    return sorted(folder.glob("*.pdf"), key=lambda p: p.name.lower())