from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
import pytesseract
from PIL import Image
import PyPDF2
from docx import Document
import openpyxl
from pdf2image import convert_from_path
import os
import re
import csv
import json
import tempfile

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()

ALLOWED_EXTENSIONS = {'pdf', 'docx', 'xlsx', 'jpg', 'jpeg', 'png', 'tiff', 'tif'}

# ----------------------------------------------------------------------
# Paths to data files (place all next to app.py)
# ----------------------------------------------------------------------
LEXICON_PATH = "lexicon_latest.csv"
REGEX_PATH = "regex_patterns.json"
STOPWORDS_PATH = "english.txt"


def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ----------------------------------------------------------------------
# Load keywords (with lengths), regex patterns, and stopwords
# ----------------------------------------------------------------------
def load_keywords():
    """
    Load keywords and their lengths from lexicon_latest.csv.
    Assumes header: keyword,length
    """
    keywords = []
    length_map = {}
    with open(LEXICON_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            kw = (row.get("keyword") or "").strip()
            if not kw:
                continue
            try:
                kw_len = int(row.get("length") or 0)
            except ValueError:
                kw_len = 0
            keywords.append(kw)
            length_map[kw.lower()] = kw_len
    return keywords, length_map


def load_regex_patterns():
    """
    Load regex patterns from regex_patterns.json.
    Expects a list of objects: { "name": "...", "pattern": "..." }.
    """
    with open(REGEX_PATH, encoding="utf-8") as f:
        data = json.load(f)

    patterns = []
    for item in data:
        name = item.get("name")
        pattern = item.get("pattern")
        if not name or not pattern:
            continue
        try:
            compiled = re.compile(pattern, re.MULTILINE)
            patterns.append(
                {
                    "name": name,
                    "pattern": pattern,
                    "regex": compiled,
                }
            )
        except re.error:
            # Skip invalid regex entries
            continue
    return patterns


def load_stopwords():
    """
    Load stopwords from english.txt (one term per line).
    """
    stopwords = set()
    with open(STOPWORDS_PATH, encoding="utf-8") as f:
        for line in f:
            w = line.strip()
            if w:
                stopwords.add(w.lower())
    return stopwords


KEYWORDS, KEYWORD_LENGTHS = load_keywords()
REGEX_PATTERNS = load_regex_patterns()
STOPWORDS = load_stopwords()

# ----------------------------------------------------------------------
# Text extraction helpers
# ----------------------------------------------------------------------
def extract_text_from_image(image_path):
    """Extract text from image using OCR (pytesseract)."""
    try:
        image = Image.open(image_path)
        text = pytesseract.image_to_string(image)
        return text
    except Exception as e:
        return f"Error extracting text from image: {str(e)}"


def extract_text_from_pdf(pdf_path):
    """Extract text from PDF (handles both text-based and image-based PDFs)."""
    text = ""
    try:
        # Try text extraction first
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            for page in reader.pages:
                page_text = page.extract_text() or ""
                text += page_text + "\n"

        # If PDF is mostly empty/scanned, convert to images and use OCR
        if len(text.strip()) < 50:
            images = convert_from_path(pdf_path)
            for image in images:
                text += pytesseract.image_to_string(image) + "\n"
    except Exception as e:
        return f"Error extracting text from PDF: {str(e)}"

    return text


def extract_text_from_docx(docx_path):
    """Extract text from Word document."""
    text = ""
    try:
        doc = Document(docx_path)
        for para in doc.paragraphs:
            text += para.text + "\n"
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    text += cell.text + "\n"
    except Exception as e:
        return f"Error extracting text from DOCX: {str(e)}"

    return text


def extract_text_from_xlsx(xlsx_path):
    """Extract text from Excel file."""
    text = ""
    try:
        wb = openpyxl.load_workbook(xlsx_path, data_only=True)
        for sheet in wb.sheetnames:
            ws = wb[sheet]
            text += f"\n[Sheet: {sheet}]\n"
            for row in ws.iter_rows(values_only=True):
                line_parts = []
                for cell in row:
                    if cell is not None:
                        line_parts.append(str(cell))
                if line_parts:
                    text += " ".join(line_parts) + "\n"
    except Exception as e:
        return f"Error extracting text from XLSX: {str(e)}"

    return text


def extract_text_from_file(filepath, filename):
    """Route to appropriate text extraction method based on extension."""
    ext = filename.rsplit('.', 1)[1].lower()

    if ext == 'pdf':
        return extract_text_from_pdf(filepath)
    elif ext == 'docx':
        return extract_text_from_docx(filepath)
    elif ext == 'xlsx':
        return extract_text_from_xlsx(filepath)
    elif ext in {'jpg', 'jpeg', 'png', 'tiff', 'tif'}:
        return extract_text_from_image(filepath)
    else:
        return "Unsupported file type"


# ----------------------------------------------------------------------
# Keyword phrase detection:
#   - Two adjacent lexicon words
#   - Same line only (no crossing \n)
#   - Exclude stopwords from english.txt
# ----------------------------------------------------------------------
WORD_SPLIT_RE = re.compile(r"\s+")


def find_adjacent_keyword_pairs(text, keywords, length_map, stopwords, case_sensitive=False):
    """
    Find matches where TWO keywords from `keywords` appear as two consecutive
    tokens on the same line. Excludes stopwords and includes combined length.
    """
    if not text:
        return []

    if not case_sensitive:
        keyword_set = {k.lower() for k in keywords}
    else:
        keyword_set = set(keywords)

    matches = []
    lines = text.splitlines()
    char_offset = 0  # global character index

    for line in lines:
        line_proc = line if case_sensitive else line.lower()

        # Tokenize line on whitespace
        tokens = []
        pos = 0
        for part in WORD_SPLIT_RE.split(line_proc):
            if not part:
                continue
            start = line_proc.find(part, pos)
            if start == -1:
                continue
            end = start + len(part)
            tokens.append((part, start, end))
            pos = end

        # Check adjacent pairs within the same line
        for i in range(len(tokens) - 1):
            w1, s1, e1 = tokens[i]
            w2, s2, e2 = tokens[i + 1]

            # Exclude stopwords
            if w1 in stopwords or w2 in stopwords:
                continue

            if w1 in keyword_set and w2 in keyword_set:
                phrase = f"{w1} {w2}"

                len1 = length_map.get(w1, 0)
                len2 = length_map.get(w2, 0)
                combined_length = len1 + len2

                global_start = char_offset + s1
                global_end = char_offset + e2

                ctx_start = max(0, global_start - 80)
                ctx_end = min(len(text), global_end + 80)
                context = text[ctx_start:ctx_end]
                if ctx_start > 0:
                    context = "..." + context
                if ctx_end < len(text):
                    context = context + "..."

                matches.append(
                    {
                        "phrase": phrase,
                        "word1": w1,
                        "word2": w2,
                        "length_word1": len1,
                        "length_word2": len2,
                        "combined_length": combined_length,
                        "context": context,
                        "position": global_start,
                    }
                )

        # +1 for the newline removed by splitlines()
        char_offset += len(line) + 1

    return matches


# ----------------------------------------------------------------------
# Regex matching with line numbers and context
# ----------------------------------------------------------------------
def find_regex_matches(text, regex_patterns, context_window=80):
    """
    For each regex pattern, return matches with:
    - name
    - pattern
    - matched text
    - line number
    - context (surrounding text)
    """
    results = []
    if not text:
        return results

    lines = text.splitlines()
    char_offset = 0  # global character index

    for line_no, line in enumerate(lines, start=1):
        for item in regex_patterns:
            regex = item["regex"]
            for m in regex.finditer(line):
                local_start = m.start()
                local_end = m.end()

                global_start = char_offset + local_start
                global_end = char_offset + local_end

                ctx_start = max(0, global_start - context_window)
                ctx_end = min(len(text), global_end + context_window)
                context = text[ctx_start:ctx_end]
                if ctx_start > 0:
                    context = "..." + context
                if ctx_end < len(text):
                    context = context + "..."

                results.append(
                    {
                        "name": item["name"],
                        "pattern": item["pattern"],
                        "match": m.group(0),
                        "line": line_no,
                        "context": context,
                    }
                )

        # +1 for newline removed by splitlines()
        char_offset += len(line) + 1

    return results


# ----------------------------------------------------------------------
# API endpoints
# ----------------------------------------------------------------------
@app.route('/scan', methods=['POST'])
def scan_documents():
    """Main endpoint for document scanning and detection."""
    try:
        if 'files' not in request.files or len(request.files.getlist('files')) == 0:
            return jsonify({'error': 'No files uploaded'}), 400

        files = request.files.getlist('files')
        case_sensitive = request.form.get('case_sensitive', 'false') == 'true'

        all_phrase_matches = []
        all_regex_matches = []
        processed_files = []
        errors = []

        for file in files:
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)

                try:
                    text = extract_text_from_file(filepath, filename)

                    # 1) adjacent keyword pairs from lexicon_latest.csv
                    phrase_matches = find_adjacent_keyword_pairs(
                        text,
                        KEYWORDS,
                        KEYWORD_LENGTHS,
                        STOPWORDS,
                        case_sensitive=case_sensitive,
                    )
                    for m in phrase_matches:
                        m["document"] = filename
                    all_phrase_matches.extend(phrase_matches)

                    # 2) regex matches from regex_patterns.json
                    regex_matches = find_regex_matches(text, REGEX_PATTERNS)
                    for r in regex_matches:
                        r["document"] = filename
                    all_regex_matches.extend(regex_matches)

                    processed_files.append(filename)

                except Exception as e:
                    errors.append(f"Error processing {filename}: {str(e)}")
                finally:
                    if os.path.exists(filepath):
                        os.remove(filepath)
            else:
                errors.append(f"File not allowed: {file.filename}")

        # Sort keyword-phrase matches by position
        all_phrase_matches.sort(key=lambda x: x.get("position", 0))

        return jsonify(
            {
                "success": True,
                "total_documents": len(processed_files),
                "documents_processed": processed_files,
                "keyword_phrase_matches_count": len(all_phrase_matches),
                "keyword_phrase_matches": all_phrase_matches,
                "regex_matches_count": len(all_regex_matches),
                "regex_matches": all_regex_matches,
                "errors": errors,
            }
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({"status": "Server is running", "ocr_available": check_tesseract()}), 200


def check_tesseract():
    """Check if Tesseract OCR is installed and reachable."""
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


if __name__ == '__main__':
    print("Starting Document Scanner Backend Server...")
    print("Server running on http://localhost:5555")
    app.run(debug=True, host='0.0.0.0', port=5555)
