#!/usr/bin/env python3
import os
import json
import tempfile
import re
import csv
import pytesseract
import cv2
from flask import Flask, request, jsonify
from PIL import Image
from PyPDF2 import PdfReader
from pdf2image import convert_from_path
from docx import Document
from openpyxl import load_workbook

# -------------------------------
# Configuration
# -------------------------------

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500MB

REGEX_FILE = "regex_patterns.json"
LEXICON_FILE = "lexicon_latest.csv"
STOPWORDS_FILE = "english.txt"

# Uncomment if needed on Windows
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# -------------------------------
# Regex loading (RAW SAFE)
# -------------------------------

def load_regex_patterns():
    """
    Loads regex patterns from JSON and compiles them exactly as written.
    No escaping, no eval, no surprises.
    """
    patterns = []
    if not os.path.exists(REGEX_FILE):
        return patterns

    with open(REGEX_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    for entry in data:
        name = entry.get("name")
        pattern_text = entry.get("pattern")

        if not name or not pattern_text:
            continue

        try:
            compiled = re.compile(pattern_text)
            patterns.append({
                "name": name,
                "pattern": pattern_text,
                "compiled": compiled
            })
        except re.error as e:
            print(f"[REGEX ERROR] {name}: {e}")

    return patterns


REGEX_PATTERNS = load_regex_patterns()


def load_keywords():
    keywords = []
    if not os.path.exists(LEXICON_FILE):
        return keywords

    with open(LEXICON_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            kw = (row.get("keyword") or "").strip()
            if kw:
                keywords.append(kw)

    return keywords


def load_stopwords():
    stopwords = set()
    if not os.path.exists(STOPWORDS_FILE):
        return stopwords

    with open(STOPWORDS_FILE, encoding="utf-8") as f:
        for line in f:
            w = line.strip()
            if w:
                stopwords.add(w.lower())

    return stopwords


LEXICON_KEYWORDS = load_keywords()
STOPWORDS = load_stopwords()

# -------------------------------
# Text Extraction Helpers
# -------------------------------

def extract_text_from_pdf(path):
    text = ""

    try:
        reader = PdfReader(path)
        for page in reader.pages:
            text += page.extract_text() or ""
    except Exception:
        pass

    # OCR fallback
    if not text.strip():
        images = convert_from_path(path)
        for img in images:
            text += pytesseract.image_to_string(img)

    return text


def extract_text_from_docx(path):
    doc = Document(path)
    return "\n".join(p.text for p in doc.paragraphs)


def extract_text_from_xlsx(path):
    wb = load_workbook(path, data_only=True)
    output = []

    for sheet in wb:
        for row in sheet.iter_rows(values_only=True):
            for cell in row:
                if cell:
                    output.append(str(cell))

    return "\n".join(output)


def extract_text_from_image(path):
    img = cv2.imread(path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return pytesseract.image_to_string(gray)


# -------------------------------
# Lexicon adjacent word detection
# -------------------------------
WORD_RE = re.compile(r"[A-Za-z0-9]+")


def find_adjacent_lexicon_pairs(text, keywords, stopwords, case_sensitive):
    results = []
    if not text or not keywords:
        return results

    keyword_set = set(keywords) if case_sensitive else {k.lower() for k in keywords}
    lines = text.splitlines()
    char_offset = 0

    for line in lines:
        line_proc = line if case_sensitive else line.lower()
        tokens = [(m.group(0), m.start(), m.end()) for m in WORD_RE.finditer(line_proc)]

        for i in range(len(tokens) - 1):
            w1, s1, e1 = tokens[i]
            w2, s2, e2 = tokens[i + 1]

            if w1.lower() in stopwords or w2.lower() in stopwords:
                continue

            if w1 not in keyword_set or w2 not in keyword_set:
                continue

            # Exactly one space between words
            if s2 != e1 + 1 or line_proc[e1] != " ":
                continue

            # No punctuation touching either word
            if (s1 > 0 and line_proc[s1 - 1] != " ") or (
                e2 < len(line_proc) and line_proc[e2] != " "
            ):
                continue

            global_start = char_offset + s1
            global_end = char_offset + e2
            context_start = max(0, global_start - 40)
            context_end = min(len(text), global_end + 40)

            results.append(
                {
                    "phrase": text[global_start:global_end],
                    "context": text[context_start:context_end].strip(),
                    "rejected": False,
                    "position": global_start,
                }
            )

        char_offset += len(line) + 1

    return results


# -------------------------------
# Flask Routes
# -------------------------------

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "Server is running",
        "ocr_available": True,
        "regex_patterns_loaded": len(REGEX_PATTERNS)
    })


@app.route("/scan", methods=["POST"])
def scan():
    files = request.files.getlist("files")

    case_sensitive = request.form.get("case_sensitive") == "true"
    mode = request.form.get("mode", "phrase")

    matches = []
    errors = []
    processed_files = []

    for file in files:
        try:
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                file.save(tmp.name)
                path = tmp.name

            ext = os.path.splitext(file.filename)[1].lower()

            if ext == ".pdf":
                text = extract_text_from_pdf(path)
            elif ext == ".docx":
                text = extract_text_from_docx(path)
            elif ext == ".xlsx":
                text = extract_text_from_xlsx(path)
            else:
                text = extract_text_from_image(path)

            processed_files.append(file.filename)

            # Lexicon adjacent word scanning only
            if mode == "phrase":
                lexicon_found = find_adjacent_lexicon_pairs(
                    text, LEXICON_KEYWORDS, STOPWORDS, case_sensitive
                )
                for f in lexicon_found:
                    f["document"] = file.filename
                matches.extend(lexicon_found)

            # Regex scanning
            for rx in REGEX_PATTERNS:
                for m in rx["compiled"].finditer(text):
                    snippet = text[max(m.start()-40, 0):m.end()+40]

                    matches.append({
                        "phrase": rx["name"],
                        "document": file.filename,
                        "context": snippet.strip(),
                        "rejected": False,
                        "position": m.start()
                    })

        except Exception as e:
            errors.append(f"{file.filename}: {str(e)}")

        finally:
            try:
                os.unlink(path)
            except Exception:
                pass

    return jsonify({
        "success": True,
        "total_documents": len(processed_files),
        "documents_processed": processed_files,
        "total_matches": len(matches),
        "matches": matches,
        "errors": errors
    })


# -------------------------------
# Entry Point
# -------------------------------

if __name__ == "__main__":
    print("Starting Document Scanner Backend Server...")
    app.run(debug=True)
