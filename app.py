import os
import csv
import json
import tempfile
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import re
import html as html_lib
from email import policy
from email.parser import BytesParser
import xml.etree.ElementTree as ET
import base64

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
CORS(app, resources={
    r"/*": {
        "origins": [
            "http://127.0.0.1:5500",
            "http://localhost:5500",
            "null",
            "file://",
        ]
    }
})

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
PROGRESS_DIR = Path(tempfile.gettempdir()) / "purview_scan_progress"
RULEPACK_CACHE_PATH = Path("rulepack_cache.json")
MAX_SIT_FILES = 50

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
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", category=PyPDF2.errors.PdfReadWarning)
        with open(path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text += page.extract_text() or ""
    seen_messages = set()
    for warning in caught:
        message = str(warning.message)
        if message in seen_messages:
            continue
        seen_messages.add(message)
        print(f"PdfReadWarning [{Path(path)}]: {message}")

    def is_garbled_text(value: str) -> bool:
        sample = value[:8000]
        if len(sample) < 200:
            return False
        tokens = re.findall(r"\S+", sample)
        if not tokens:
            return False
        weird_token_count = 0
        for token in tokens:
            if re.search(r"[\\^`\\[\\]{}]", token):
                weird_token_count += 1
                continue
            if re.search(r"[^A-Za-z0-9.,;:'\"()\\/&%$@#!?\-]", token):
                weird_token_count += 1
        if (weird_token_count / len(tokens)) > 0.15:
            return True
        weird_chars = sum(1 for ch in sample if ch in "\\[]{}^`")
        return (weird_chars / len(sample)) > 0.01

    if text.strip() and not is_garbled_text(text):
        return text

    if text.strip():
        print(f"PDF OCR fallback [{Path(path)}]: garbled_text")
        text = ""

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
                if isinstance(saved_path, (tuple, list)):
                    saved_path = next(
                        (item for item in saved_path if isinstance(item, (str, bytes))),
                        None,
                    )
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
    scenario_mode = request.form.get("scenario_mode", "sit").strip().lower()
    scan_id = request.form.get("scan_id")
    scan_path = request.form.get("path")
    recursive = request.form.get("recursive", "true").lower() == "true"
    log_path = request.form.get("log_path")
    log_to_stdout = request.form.get("log_stdout", "true").lower() == "true"
    debug_text = request.form.get("debug_text", "false").lower() == "true"
    debug_text_path = request.form.get("debug_text_path")
    def normalize_output_path(value, default):
        if value is None:
            return default
        value = value.strip()
        if not value:
            return default
        if value.lower() in {"none", "null", "false"}:
            return None
        return value

    regex_output_path = normalize_output_path(
        request.form.get("regex_output_path"),
        "regex_matches.csv",
    )
    keyword_output_path = normalize_output_path(
        request.form.get("keyword_output_path"),
        "keyword_matches.csv",
    )
    if scenario_mode == "scan_only":
        keyword_output_path = None
    allowed_exts = parse_file_types(request.form.get("file_types"))
    output_path = request.form.get("output_path")
    batch_size = int(request.form.get("batch_size", "500"))
    return_limit = int(request.form.get("return_limit", "0"))

    if not lexicon_path:
        lexicon_path = DEFAULT_LEXICON_PATH
    if not regex_path:
        regex_path = REGEX_PATTERNS_PATH

    if scenario_mode not in {"sit", "scan_only"}:
        return jsonify({
            "success": False,
            "error": "scenario_mode must be 'sit' or 'scan_only'"
        }), 400

    progress_path = None
    if scan_id and re.fullmatch(r"[A-Za-z0-9_-]{6,64}", scan_id):
        PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
        progress_path = PROGRESS_DIR / f"{scan_id}.json"

    def write_progress(payload):
        if not progress_path:
            return
        payload["scan_id"] = scan_id
        with open(progress_path, "w", encoding="utf-8") as f:
            json.dump(payload, f)

    if progress_path:
        write_progress({
            "status": "starting",
            "current": 0,
            "total": 0,
            "percent": 0,
            "current_document": "Listing files..."
        })

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

    temp_files = []

    def cleanup_temp_files():
        for path in temp_files:
            try:
                os.remove(path)
            except OSError:
                pass

    def save_uploaded_file(upload, suffix):
        if not upload or not upload.filename:
            return None
        ext = Path(upload.filename).suffix.lower()
        final_suffix = ext if ext else suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=final_suffix) as tmp:
            upload.save(tmp.name)
            temp_files.append(tmp.name)
            return tmp.name

    uploaded_lexicon = request.files.get("lexicon_file")
    uploaded_regex = request.files.get("regex_file")
    lexicon_upload_path = save_uploaded_file(uploaded_lexicon, ".csv")
    regex_upload_path = save_uploaded_file(uploaded_regex, ".json")
    if lexicon_upload_path:
        lexicon_path = lexicon_upload_path
    if regex_upload_path:
        regex_path = regex_upload_path

    scan_items = []
    listing_count = 0
    for scan_item in iter_scan_items(
        request.files.getlist("files"),
        scan_path,
        recursive,
        allowed_exts,
    ):
        scan_items.append(scan_item)
        listing_count += 1
        if scan_path and listing_count % 50 == 0:
            write_progress({
                "status": "listing",
                "current": listing_count,
                "total": 0,
                "percent": 0,
                "current_document": f"Found {listing_count} files..."
            })
    total_documents = listing_count
    if scenario_mode == "sit" and (total_documents == 0 or total_documents > MAX_SIT_FILES):
        write_progress({
            "status": "error",
            "error": f"Scenario 1 requires 1-{MAX_SIT_FILES} files. Found {total_documents}."
        })
        cleanup_temp_files()
        if log_file:
            log_file.close()
        if debug_file:
            debug_file.close()
        return jsonify({
            "success": False,
            "error": f"Scenario 1 requires 1-{MAX_SIT_FILES} files. Found {total_documents}."
        }), 400
    write_progress({
        "status": "running" if total_documents > 0 else "complete",
        "current": 0,
        "total": total_documents,
        "percent": 0 if total_documents > 0 else 100,
        "current_document": "" if total_documents > 0 else "No files found"
    })

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
    if keyword_output_path and scenario_mode == "sit":
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
        write_progress({
            "status": "error",
            "error": f"regex_path not found: {regex_path}"
        })
        cleanup_temp_files()
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

    keywords = []
    keyword_set = set()
    if scenario_mode == "sit":
        keywords = load_keywords(lexicon_path)
        keyword_set = set(keywords)
    regex_patterns = load_regex_patterns(regex_path)
    # Keep debug_text focused on extracted document text only.

    warned_regex_csv_disabled = False
    sit_outputs = None
    if scenario_mode == "sit":
        def increment_version(value: str) -> str:
            if not value:
                return "1.0"
            parts = value.split(".")
            if not all(part.isdigit() for part in parts):
                return value
            parts[-1] = str(int(parts[-1]) + 1)
            return ".".join(parts)

        sit_outputs = {
            "sit_name": request.form.get("sit_name", "").strip() or "Custom SIT",
            "sit_description": request.form.get("sit_description", "").strip(),
            "sit_publisher": request.form.get("sit_publisher", "").strip() or "Purview Custom",
            "rule_pack_name": request.form.get("rule_pack_name", "").strip() or "CustomRulePack",
        }
        rule_pack_mode = request.form.get("rule_pack_mode", "new").strip().lower()
        increment_rule_pack_version = (
            request.form.get("increment_rule_pack_version", "true").strip().lower()
            == "true"
        )
        uploaded_rule_pack = request.files.get("rule_pack_file")
        rule_pack_base64 = request.form.get("rule_pack_base64", "").strip()

        regex_xml_entries = []
        for r in regex_patterns:
            regex_name = html_lib.escape(r.get("name", "Regex"))
            regex_pattern = html_lib.escape(r.get("pattern", ""))
            regex_xml_entries.append(
                f'    <Regex name="{regex_name}" pattern="{regex_pattern}" />'
            )
        regex_xml = "\n".join(regex_xml_entries) if regex_xml_entries else "    <!-- No regex patterns found -->"
        if uploaded_rule_pack and uploaded_rule_pack.filename:
            rule_pack_bytes = uploaded_rule_pack.read()
        elif rule_pack_base64:
            try:
                rule_pack_bytes = base64.b64decode(rule_pack_base64)
            except (ValueError, TypeError) as exc:
                return jsonify({
                    "success": False,
                    "error": f"invalid rule_pack_base64: {exc}"
                }), 400
        else:
            rule_pack_bytes = None
        if rule_pack_bytes:
            try:
                root = ET.fromstring(rule_pack_bytes)
            except ET.ParseError as exc:
                write_progress({
                    "status": "error",
                    "error": f"invalid rule pack xml: {exc}"
                })
                cleanup_temp_files()
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
                    "error": f"invalid rule pack xml: {exc}"
                }), 400

            rule_pack_info = root.find("RulePackInfo")
            if rule_pack_info is None:
                rule_pack_info = ET.SubElement(root, "RulePackInfo")
            if sit_outputs["rule_pack_name"]:
                rule_pack_info.set("name", sit_outputs["rule_pack_name"])
            if sit_outputs["sit_publisher"]:
                rule_pack_info.set("publisher", sit_outputs["sit_publisher"])
            if increment_rule_pack_version:
                current_version = rule_pack_info.get("version", "")
                rule_pack_info.set("version", increment_version(current_version))

            sit_parent = root.find("SensitiveInformationTypes")
            if sit_parent is None:
                sit_parent = ET.SubElement(root, "SensitiveInformationTypes")

            existing = None
            for child in sit_parent.findall("SensitiveInformationType"):
                if child.get("name") == sit_outputs["sit_name"]:
                    existing = child
                    break

            if rule_pack_mode == "update":
                if existing is None:
                    return jsonify({
                        "success": False,
                        "error": f"SIT not found in rule pack: {sit_outputs['sit_name']}"
                    }), 400
                target = existing
            else:
                if existing is not None:
                    return jsonify({
                        "success": False,
                        "error": f"SIT already exists in rule pack: {sit_outputs['sit_name']}"
                    }), 400
                target = ET.SubElement(
                    sit_parent, "SensitiveInformationType", {"name": sit_outputs["sit_name"]}
                )

            if sit_outputs["sit_description"]:
                description = target.find("Description")
                if description is None:
                    description = ET.SubElement(target, "Description")
                description.text = sit_outputs["sit_description"]

            regexes = target.find("Regexes")
            if regexes is None:
                regexes = ET.SubElement(target, "Regexes")
            else:
                regexes.clear()
            if regex_patterns:
                for r in regex_patterns:
                    ET.SubElement(
                        regexes,
                        "Regex",
                        {
                            "name": r.get("name", "Regex"),
                            "pattern": r.get("pattern", ""),
                        },
                    )
            else:
                regexes.append(ET.Comment("No regex patterns found"))

            sit_outputs["rule_pack_xml"] = ET.tostring(
                root, encoding="utf-8", xml_declaration=True
            ).decode("utf-8")
        else:
            sit_outputs["rule_pack_xml"] = (
                "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n"
                "<RulePack>\n"
                f"  <RulePackInfo name=\"{html_lib.escape(sit_outputs['rule_pack_name'])}\" "
                f"publisher=\"{html_lib.escape(sit_outputs['sit_publisher'])}\" version=\"1.0\" />\n"
                "  <SensitiveInformationTypes>\n"
                f"    <SensitiveInformationType name=\"{html_lib.escape(sit_outputs['sit_name'])}\">\n"
                f"      <Description>{html_lib.escape(sit_outputs['sit_description'])}</Description>\n"
                "      <Regexes>\n"
                f"{regex_xml}\n"
                "      </Regexes>\n"
                "    </SensitiveInformationType>\n"
                "  </SensitiveInformationTypes>\n"
                "</RulePack>\n"
            )

        sit_outputs["powershell_script"] = (
            "$rulePackPath = \"./"
            + sit_outputs["rule_pack_name"]
            + ".xml\"\n"
            "Write-Host \"Importing rule pack: $rulePackPath\"\n"
            "New-DlpSensitiveInformationTypeRulePackage -FileData "
            "(Get-Content -Path $rulePackPath -Encoding Byte -ReadCount 0)\n"
        )

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

    for source, item in scan_items:
        documents_scanned += 1
        try:
            if source == "upload":
                document = item.filename
            else:
                document = str(item)

            if total_documents > 0:
                write_progress({
                    "status": "running",
                    "current": documents_scanned,
                    "total": total_documents,
                    "percent": int((documents_scanned / total_documents) * 100),
                    "current_document": document
                })

            if source == "upload":
                text = extract_text_from_upload(item)
            else:
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
            if regex_hits and scenario_mode == "sit":
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
            if regex_hits and not regex_csv_writer and not warned_regex_csv_disabled:
                log("warning: regex_output_path disabled; regex CSV not written")
                warned_regex_csv_disabled = True
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
    cleanup_temp_files()
    write_progress({
        "status": "complete",
        "current": documents_scanned,
        "total": total_documents,
        "percent": 100,
        "current_document": ""
    })

    return jsonify({
        "success": True,
        "scenario_mode": scenario_mode,
        "sit_outputs": sit_outputs,
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


@app.route("/", methods=["GET"])
def index():
    return send_from_directory(".", "index.html")


@app.route("/index.html", methods=["GET"])
def index_html():
    return send_from_directory(".", "index.html")

@app.route("/regex-files", methods=["GET"])
def regex_files():
    root = Path(".").resolve()
    files = []
    try:
        for path in root.glob("regex_patterns*.json"):
            if path.is_file():
                files.append(path.name)
                if len(files) >= 200:
                    break
    except OSError:
        pass
    files.sort()
    return jsonify({"success": True, "files": files})


@app.route("/lexicon-files", methods=["GET"])
def lexicon_files():
    root = Path(".").resolve()
    files = []
    try:
        for path in root.glob("lexicon*.csv"):
            if path.is_file():
                files.append(path.name)
                if len(files) >= 200:
                    break
    except OSError:
        pass
    files.sort()
    return jsonify({"success": True, "files": files})

@app.route("/rulepack-cache", methods=["GET"])
def rulepack_cache():
    if not RULEPACK_CACHE_PATH.is_file():
        return jsonify({
            "success": False,
            "error": "rule pack cache not found"
        }), 404
    try:
        with open(RULEPACK_CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return jsonify({
            "success": False,
            "error": f"unable to read rule pack cache: {exc}"
        }), 400
    return jsonify({"success": True, "cache": data})

@app.route("/progress/<scan_id>", methods=["GET"])
def progress(scan_id):
    if not re.fullmatch(r"[A-Za-z0-9_-]{6,64}", scan_id):
        return jsonify({"success": False, "error": "invalid scan_id"}), 400
    progress_path = PROGRESS_DIR / f"{scan_id}.json"
    if not progress_path.is_file():
        return jsonify({"success": False, "error": "scan_id not found"}), 404
    with open(progress_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["success"] = True
    return jsonify(data)


if __name__ == "__main__":
    print("Starting Document Scanner Backend Server...")
    port = int(os.environ.get("PORT", "5000"))
    app.run(debug=True, use_reloader=False, port=port)
