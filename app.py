import os
import csv
import json
import tempfile
from pathlib import Path
from flask import Flask, request, jsonify
import re

import pytesseract
from PIL import Image
import PyPDF2
import docx
import openpyxl
from pdf2image import convert_from_path

# ======================================================
# Flask app
# ======================================================

app = Flask(__name__)

# ======================================================
# Configuration
# ======================================================

DEFAULT_LEXICON_PATH = "lexicon_latest.csv"
REGEX_PATTERNS_PATH = "regex_patterns.json"

SUPPORTED_EXTENSIONS = {
    ".pdf", ".docx", ".xlsx",
    ".jpg", ".jpeg", ".png", ".tif", ".tiff"
}

app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500MB

# ======================================================
# Lexicon loading (STRICT multi-word only)
# ======================================================

def load_keywords(lexicon_path: str = DEFAULT_LEXICON_PATH):
    keywords = []

    with open(lexicon_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            value = (
                row.get("keyword")
                or row.get("phrase")
                or row.get("value")
            )
            if not value:
                continue

            value = value.strip()

            # At least two words, single literal spaces, alnum only
            if re.fullmatch(r"[A-Za-z0-9]+( [A-Za-z0-9]+)+", value):
                keywords.append(value)

    return keywords

# ======================================================
# Regex loading
# ======================================================

def load_regex_patterns(regex_path: str = REGEX_PATTERNS_PATH):
    with open(regex_path, encoding="utf-8") as f:
        return json.load(f)

# ======================================================
# File collection
# ======================================================

def collect_files_from_path(path: str, recursive: bool):
    collected = []
    p = Path(path)

    if p.is_file():
        if p.suffix.lower() in SUPPORTED_EXTENSIONS:
            collected.append(p)
        return collected

    if p.is_dir():
        iterator = p.rglob("*") if recursive else p.glob("*")
        for item in iterator:
            if item.is_file() and item.suffix.lower() in SUPPORTED_EXTENSIONS:
                collected.append(item)

    return collected

def parse_file_types(value: str):
    if not value:
        return None
    types = set()
    for item in value.split(","):
        ext = item.strip().lower()
        if not ext:
            continue
        if not ext.startswith("."):
            ext = "." + ext
        types.add(ext)
    return types or None

def allowed_extension(ext: str, allowed_exts):
    if allowed_exts is None:
        return ext in SUPPORTED_EXTENSIONS
    return ext in allowed_exts

# ======================================================
# Text extraction
# ======================================================

def extract_text_from_pdf(path):
    text = ""
    with open(path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            text += page.extract_text() or ""

    if text.strip():
        return text

    images = convert_from_path(path)
    for img in images:
        text += pytesseract.image_to_string(img)

    return text


def extract_text_from_docx(path):
    doc = docx.Document(path)
    return "\n".join(p.text for p in doc.paragraphs)


def extract_text_from_xlsx(path):
    wb = openpyxl.load_workbook(path, data_only=True)
    text = ""
    for sheet in wb.worksheets:
        for row in sheet.iter_rows(values_only=True):
            for cell in row:
                if cell is not None:
                    text += f"{cell} "
    return text


def extract_text_from_image(path):
    img = Image.open(path)
    return pytesseract.image_to_string(img)


def extract_text_from_file_path(path: Path):
    ext = path.suffix.lower()
    if ext == ".pdf":
        return extract_text_from_pdf(str(path))
    if ext == ".docx":
        return extract_text_from_docx(str(path))
    if ext == ".xlsx":
        return extract_text_from_xlsx(str(path))
    if ext in {".jpg", ".jpeg", ".png", ".tif", ".tiff"}:
        return extract_text_from_image(str(path))
    return ""


def extract_text_from_upload(file):
    suffix = Path(file.filename).suffix.lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        file.save(tmp.name)
        return extract_text_from_file_path(Path(tmp.name))

# ======================================================
# Proximity logic
# ======================================================

def nearest_regex_info(start, end, regex_hits):
    closest = None
    min_distance = None

    for r in regex_hits:
        if r["end"] < start:
            d = start - r["end"]
        elif r["start"] > end:
            d = r["start"] - end
        else:
            d = 0

        if min_distance is None or d < min_distance:
            min_distance = d
            closest = r["name"]

    return closest, min_distance

# ======================================================
# API endpoint
# ======================================================

@app.route("/scan", methods=["POST"])
def scan():
    lexicon_path = request.form.get("lexicon_path", DEFAULT_LEXICON_PATH)
    regex_path = request.form.get("regex_path", REGEX_PATTERNS_PATH)
    scan_path = request.form.get("path")
    recursive = request.form.get("recursive", "true").lower() == "true"
    log_path = request.form.get("log_path")
    log_to_stdout = request.form.get("log_stdout", "true").lower() == "true"
    allowed_exts = parse_file_types(request.form.get("file_types"))

    log_file = None
    if log_path:
        log_file = open(log_path, "a", encoding="utf-8")

    def log(line: str):
        if log_to_stdout:
            print(line)
        if log_file:
            log_file.write(line + "\n")
            log_file.flush()

    if not os.path.isfile(regex_path):
        if log_file:
            log_file.close()
        return jsonify({
            "success": False,
            "error": f"regex_path not found: {regex_path}"
        }), 400

    keywords = load_keywords(lexicon_path)
    regex_patterns = load_regex_patterns(regex_path)

    all_files = []

    for f in request.files.getlist("files"):
        ext = Path(f.filename).suffix.lower()
        if allowed_extension(ext, allowed_exts):
            all_files.append(("upload", f))

    if scan_path:
        for p in collect_files_from_path(scan_path, recursive):
            if allowed_extension(p.suffix.lower(), allowed_exts):
                all_files.append(("path", p))

    results = []
    errors = []

    for source, item in all_files:
        try:
            if source == "upload":
                document = item.filename
                text = extract_text_from_upload(item)
            else:
                document = str(item)
                text = extract_text_from_file_path(item)

            # -------------------------
            # Regex hits
            # -------------------------
            regex_hits = []
            for r in regex_patterns:
                for m in re.finditer(r["pattern"], text, re.IGNORECASE | re.DOTALL):
                    regex_hits.append({
                        "name": r["name"],
                        "start": m.start(),
                        "end": m.end(),
                        "value": m.group(0)
                    })

            # -------------------------
            # Keyword hits (strict)
            # -------------------------
            keyword_hits = []
            for kw in keywords:
                pat = re.compile(rf"\b{re.escape(kw)}\b")
                for m in pat.finditer(text):
                    keyword_hits.append({
                        "phrase": kw,
                        "start": m.start(),
                        "end": m.end()
                    })

            # -------------------------
            # Primary correlation mode
            # -------------------------
            if regex_hits and keyword_hits:
                logged_file = False
                for k in keyword_hits:
                    nearest_name, nearest_dist = nearest_regex_info(
                        k["start"], k["end"], regex_hits
                    )

                    if not logged_file:
                        log(f"matched_file: {document}")
                        logged_file = True
                    log(
                        f"match: keyword={k['phrase']} "
                        f"document={document} "
                        f"nearest_regex={nearest_name} "
                        f"distance={nearest_dist}"
                    )
                    results.append({
                        "type": "keyword",
                        "fallback": False,
                        "phrase": k["phrase"],
                        "document": document,
                        "position": k["start"],
                        "nearest_regex": nearest_name,
                        "nearest_regex_distance": nearest_dist,
                        "context": text[max(0, k["start"]-50):k["end"]+50]
                    })

            # -------------------------
            # Fallback mode
            # -------------------------
            else:
                logged_file = False
                for r in regex_hits:
                    if not logged_file:
                        log(f"matched_file: {document}")
                        logged_file = True
                    log(
                        f"match: regex={r['name']} "
                        f"document={document} "
                        f"value={r['value']}"
                    )
                    results.append({
                        "type": "regex",
                        "fallback": True,
                        "regex_name": r["name"],
                        "document": document,
                        "position": r["start"],
                        "value": r["value"],
                        "context": text[max(0, r["start"]-50):r["end"]+50]
                    })

                for k in keyword_hits:
                    if not logged_file:
                        log(f"matched_file: {document}")
                        logged_file = True
                    log(
                        f"match: keyword={k['phrase']} "
                        f"document={document}"
                    )
                    results.append({
                        "type": "keyword",
                        "fallback": True,
                        "phrase": k["phrase"],
                        "document": document,
                        "position": k["start"],
                        "context": text[max(0, k["start"]-50):k["end"]+50]
                    })

        except Exception as e:
            errors.append(f"{document}: {str(e)}")
            log(f"error: document={document} error={e}")

    if log_file:
        log_file.close()

    return jsonify({
        "success": True,
        "documents_scanned": len(all_files),
        "total_matches": len(results),
        "matches": results,
        "errors": errors
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "ocr_available": True
    })


if __name__ == "__main__":
    print("Starting Document Scanner Backend Server...")
    app.run(debug=True)
