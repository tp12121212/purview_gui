import os
import csv
import json
import tempfile
from pathlib import Path
from flask import Flask, request, jsonify
from flask_cors import CORS
import re
import html as html_lib
from email import policy
from email.parser import BytesParser

import pytesseract
from PIL import Image
import PyPDF2
import docx
import openpyxl
from pdf2image import convert_from_path
import extract_msg
import warnings

# ======================================================
# Flask app
# ======================================================

app = Flask(__name__)
CORS(app)

# Allow large images while keeping a sane cap to avoid DoS warnings.
Image.MAX_IMAGE_PIXELS = 200_000_000
warnings.filterwarnings(
    "ignore",
    category=Image.DecompressionBombWarning,
)

# ======================================================
# Configuration
# ======================================================

DEFAULT_LEXICON_PATH = "lexicon_latest.csv"
REGEX_PATTERNS_PATH = "regex_patterns.json"

SUPPORTED_EXTENSIONS = {
    ".pdf", ".docx", ".xlsx",
    ".jpg", ".jpeg", ".png", ".tif", ".tiff",
    ".eml", ".msg"
}

app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500MB
MAX_NESTED_DEPTH = 2

# ======================================================
# Lexicon loading (single-word only)
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

            # Single word, alnum only
            if re.fullmatch(r"[A-Za-z0-9]+", value):
                keywords.append(value.lower())

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
# Scan iteration
# ======================================================

def iter_scan_items(files, scan_path: str, recursive: bool, allowed_exts):
    for f in files:
        ext = Path(f.filename).suffix.lower()
        if allowed_extension(ext, allowed_exts):
            yield ("upload", f)

    if scan_path:
        for p in collect_files_from_path(scan_path, recursive):
            if allowed_extension(p.suffix.lower(), allowed_exts):
                yield ("path", p)

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

def strip_html(text):
    if not text:
        return ""
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", text)
    text = re.sub(r"(?is)<.*?>", " ", text)
    return html_lib.unescape(text)

def extract_text_from_attachment_bytes(filename, content, depth):
    if depth > MAX_NESTED_DEPTH:
        return ""
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        return ""
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(content)
        tmp.flush()
        return extract_text_from_file_path(Path(tmp.name), depth=depth)

def extract_text_from_eml_bytes(content, depth):
    if depth > MAX_NESTED_DEPTH:
        return ""
    msg = BytesParser(policy=policy.default).parsebytes(content)
    parts = []
    for part in msg.walk():
        if part.is_multipart():
            continue
        content_disposition = part.get_content_disposition()
        filename = part.get_filename()
        content_type = part.get_content_type()

        if content_disposition in {"attachment", "inline"} or filename:
            if filename:
                payload = part.get_payload(decode=True)
                if payload:
                    parts.append(
                        extract_text_from_attachment_bytes(
                            filename, payload, depth + 1
                        )
                    )
            continue

        if content_type == "text/plain":
            try:
                parts.append(part.get_content())
            except (LookupError, UnicodeDecodeError):
                payload = part.get_payload(decode=True) or b""
                parts.append(payload.decode(errors="ignore"))
        elif content_type == "text/html":
            try:
                parts.append(strip_html(part.get_content()))
            except (LookupError, UnicodeDecodeError):
                payload = part.get_payload(decode=True) or b""
                parts.append(strip_html(payload.decode(errors="ignore")))

    return "\n".join(p for p in parts if p)

def extract_text_from_eml_path(path, depth):
    with open(path, "rb") as f:
        return extract_text_from_eml_bytes(f.read(), depth=depth)

def extract_text_from_msg_path(path, depth):
    if depth > MAX_NESTED_DEPTH:
        return ""
    msg = extract_msg.Message(path)
    parts = []
    try:
        if msg.body:
            parts.append(msg.body)
        elif msg.htmlBody:
            parts.append(strip_html(msg.htmlBody))
        with tempfile.TemporaryDirectory() as tmpdir:
            for attachment in msg.attachments:
                filename = (
                    attachment.longFilename
                    or attachment.shortFilename
                    or attachment.filename
                )
                if not filename:
                    continue
                saved_path = attachment.save(customPath=tmpdir)
                if saved_path:
                    parts.append(
                        extract_text_from_file_path(
                            Path(saved_path), depth=depth + 1
                        )
                    )
    finally:
        msg.close()

    return "\n".join(p for p in parts if p)


def extract_text_from_file_path(path: Path, depth=0):
    ext = path.suffix.lower()
    if ext == ".pdf":
        return extract_text_from_pdf(str(path))
    if ext == ".docx":
        return extract_text_from_docx(str(path))
    if ext == ".xlsx":
        return extract_text_from_xlsx(str(path))
    if ext in {".jpg", ".jpeg", ".png", ".tif", ".tiff"}:
        return extract_text_from_image(str(path))
    if ext == ".eml":
        return extract_text_from_eml_path(str(path), depth=depth)
    if ext == ".msg":
        return extract_text_from_msg_path(str(path), depth=depth)
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
    debug_text = request.form.get("debug_text", "false").lower() == "true"
    debug_text_path = request.form.get("debug_text_path")
    regex_output_path = request.form.get("regex_output_path") or "regex_matches.csv"
    keyword_output_path = request.form.get("keyword_output_path") or "keyword_matches.csv"
    allowed_exts = parse_file_types(request.form.get("file_types"))
    output_path = request.form.get("output_path")
    batch_size = int(request.form.get("batch_size", "500"))
    return_limit = int(request.form.get("return_limit", "0"))

    log_file = None
    if log_path:
        log_file = open(log_path, "a", encoding="utf-8")

    debug_file = None
    if debug_text:
        if not debug_text_path:
            debug_text_path = "extracted_text.log"
        if output_path and os.path.abspath(debug_text_path) == os.path.abspath(output_path):
            if log_file:
                log_file.close()
            return jsonify({
                "success": False,
                "error": "debug_text_path must be different from output_path"
            }), 400
        debug_file = open(debug_text_path, "a", encoding="utf-8")

    regex_csv_file = None
    regex_csv_writer = None
    if regex_output_path:
        regex_csv_file = open(regex_output_path, "a", encoding="utf-8", newline="")
        regex_csv_writer = csv.DictWriter(
            regex_csv_file,
            fieldnames=[
                "regex_name",
                "document",
                "position",
                "value",
                "context",
            ],
        )
        if os.path.getsize(regex_output_path) == 0:
            regex_csv_writer.writeheader()

    keyword_csv_file = None
    keyword_csv_writer = None
    if keyword_output_path:
        keyword_csv_file = open(keyword_output_path, "a", encoding="utf-8", newline="")
        keyword_csv_writer = csv.DictWriter(
            keyword_csv_file,
            fieldnames=[
                "phrase",
                "document",
                "position",
                "context",
                "nearest_regex",
                "nearest_regex_distance",
            ],
        )
        if os.path.getsize(keyword_output_path) == 0:
            keyword_csv_writer.writeheader()

    def log(line: str):
        if log_to_stdout:
            print(line)
        if log_file:
            log_file.write(line + "\n")
            log_file.flush()

    def log_debug_text(line: str):
        if debug_file:
            debug_file.write(line + "\n")
            debug_file.flush()

    if not os.path.isfile(regex_path):
        if log_file:
            log_file.close()
        if debug_file:
            debug_file.close()
        if regex_csv_file:
            regex_csv_file.close()
        if keyword_csv_file:
            keyword_csv_file.close()
        return jsonify({
            "success": False,
            "error": f"regex_path not found: {regex_path}"
        }), 400

    keywords = load_keywords(lexicon_path)
    keyword_set = set(keywords)
    regex_patterns = load_regex_patterns(regex_path)
    # Keep debug_text focused on extracted document text only.

    output_file = None
    if output_path:
        output_file = open(output_path, "a", encoding="utf-8")

    results = []
    batch_results = []
    errors = []
    documents_scanned = 0
    total_matches = 0

    def record_match(item):
        nonlocal total_matches
        total_matches += 1

        if output_file:
            batch_results.append(item)
            if len(batch_results) >= batch_size:
                output_file.write("\n".join(json.dumps(r) for r in batch_results))
                output_file.write("\n")
                output_file.flush()
                batch_results.clear()

        if not output_file or (return_limit > 0 and len(results) < return_limit):
            results.append(item)

    for source, item in iter_scan_items(
        request.files.getlist("files"),
        scan_path,
        recursive,
        allowed_exts,
    ):
        documents_scanned += 1
        try:
            if source == "upload":
                document = item.filename
                text = extract_text_from_upload(item)
            else:
                document = str(item)
                text = extract_text_from_file_path(item)

            if debug_text:
                log_debug_text(f"extracted_text_begin: {document}")
                log_debug_text(text)
                log_debug_text(f"extracted_text_end: {document}")

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
            # Keyword hits (strict), only after a regex match exists
            # -------------------------
            keyword_hits = []
            if regex_hits:
                token_iter = list(re.finditer(r"[A-Za-z0-9]+", text))
                for idx in range(len(token_iter) - 1):
                    first = token_iter[idx]
                    second = token_iter[idx + 1]
                    between = text[first.end():second.start()]
                    if between != " ":
                        continue
                    w1 = first.group(0).lower()
                    w2 = second.group(0).lower()
                    if w1 in keyword_set and w2 in keyword_set:
                        keyword_hits.append({
                            "phrase": f"{w1} {w2}",
                            "start": first.start(),
                            "end": second.end()
                        })

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
                record_match({
                    "type": "regex",
                    "fallback": False,
                    "regex_name": r["name"],
                    "document": document,
                    "position": r["start"],
                    "value": r["value"],
                    "context": text[max(0, r["start"]-50):r["end"]+50]
                })
                if regex_csv_writer:
                    regex_csv_writer.writerow({
                        "regex_name": r["name"],
                        "document": document,
                        "position": r["start"],
                        "value": r["value"],
                        "context": text[max(0, r["start"]-50):r["end"]+50],
                    })

            for k in keyword_hits:
                if not logged_file:
                    log(f"matched_file: {document}")
                    logged_file = True
                nearest_name = None
                nearest_dist = None
                if regex_hits:
                    nearest_name, nearest_dist = nearest_regex_info(
                        k["start"], k["end"], regex_hits
                    )
                log(
                    f"match: keyword={k['phrase']} "
                    f"document={document}"
                )
                record_match({
                    "type": "keyword",
                    "fallback": False,
                    "phrase": k["phrase"],
                    "document": document,
                    "position": k["start"],
                    "nearest_regex": nearest_name,
                    "nearest_regex_distance": nearest_dist,
                    "context": text[max(0, k["start"]-50):k["end"]+50]
                })
                if keyword_csv_writer:
                    keyword_csv_writer.writerow({
                        "phrase": k["phrase"],
                        "document": document,
                        "position": k["start"],
                        "context": text[max(0, k["start"]-50):k["end"]+50],
                        "nearest_regex": nearest_name,
                        "nearest_regex_distance": nearest_dist,
                    })

        except Exception as e:
            errors.append(f"{document}: {str(e)}")
            log(f"error: document={document} error={e}")

    if output_file and batch_results:
        output_file.write("\n".join(json.dumps(r) for r in batch_results))
        output_file.write("\n")
        output_file.flush()
        batch_results.clear()

    if output_file:
        output_file.close()

    if log_file:
        log_file.close()
    if debug_file:
        debug_file.close()
    if regex_csv_file:
        regex_csv_file.close()
    if keyword_csv_file:
        keyword_csv_file.close()

    return jsonify({
        "success": True,
        "documents_scanned": documents_scanned,
        "total_matches": total_matches,
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
