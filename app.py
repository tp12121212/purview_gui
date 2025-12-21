#!/usr/bin/env python3
import os
import json
import tempfile
import re
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
# Phrase / Keyword Detection
# -------------------------------

def find_phrases(text, phrases, reject_words, case_sensitive, whole_word):
    results = []

    flags = 0 if case_sensitive else re.IGNORECASE

    for phrase in phrases:
        escaped = re.escape(phrase)
        pattern = escaped

        if whole_word:
            pattern = rf"\b{escaped}\b"

        for match in re.finditer(pattern, text, flags):
            start = max(match.start() - 40, 0)
            end = min(match.end() + 40, len(text))
            context = text[start:end]

            rejected = any(
                re.search(rw, context, flags=re.IGNORECASE)
                for rw in reject_words
            )

            results.append({
                "phrase": phrase,
                "context": context.strip(),
                "rejected": rejected,
                "position": match.start()
            })

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

    keywords = request.form.get("keywords", "").splitlines()
    reject_words = request.form.get("reject_words", "").splitlines()

    case_sensitive = request.form.get("case_sensitive") == "true"
    whole_word = request.form.get("whole_word") == "true"
    mode = request.form.get("mode", "phrase")

    matches = []
    keyword_matches = []
    multi_word_keyword_matches = []
    regex_matches = []
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

            # Regex scanning (collected first for proximity calculations)
            file_regex_matches = []
            for rx in REGEX_PATTERNS:
                for m in rx["compiled"].finditer(text):
                    snippet = text[max(m.start()-40, 0):m.end()+40]

                    regex_match = {
                        "phrase": rx["name"],
                        "pattern": rx["pattern"],
                        "document": file.filename,
                        "context": snippet.strip(),
                        "rejected": False,
                        "position": m.start()
                    }

                    matches.append(regex_match)
                    regex_matches.append(regex_match)
                    file_regex_matches.append(regex_match)

            # Keyword / phrase scanning
            if mode == "phrase":
                found = find_phrases(
                    text, keywords, reject_words,
                    case_sensitive, whole_word
                )

                phrase_counts = {}
                for f in found:
                    phrase_counts[f["phrase"]] = phrase_counts.get(f["phrase"], 0) + 1

                for f in found:
                    f["document"] = file.filename
                    f["instance_count"] = phrase_counts[f["phrase"]]

                    proximities = [
                        {
                            "regex_name": rx_match["phrase"],
                            "regex_pattern": rx_match["pattern"],
                            "distance": abs(f["position"] - rx_match["position"]),
                            "regex_position": rx_match["position"],
                            "regex_context": rx_match["context"]
                        }
                        for rx_match in file_regex_matches
                    ]

                    proximities.sort(key=lambda p: p["distance"])

                    f["regex_proximity"] = proximities
                    f["surrounding_text"] = f.get("context", "")

                    if re.search(r"\s", f["phrase"]):
                        multi_word_keyword_matches.append(dict(f))

                matches.extend(found)
                keyword_matches.extend(found)

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
        "total_keyword_matches": len(keyword_matches),
        "total_multi_word_keyword_matches": len(multi_word_keyword_matches),
        "total_regex_matches": len(regex_matches),
        "keyword_matches": keyword_matches,
        "multi_word_keyword_matches": multi_word_keyword_matches,
        "regex_matches": regex_matches,
        "matches": matches,
        "errors": errors
    })


# -------------------------------
# Entry Point
# -------------------------------

if __name__ == "__main__":
    print("Starting Document Scanner Backend Server...")
    app.run(debug=True)
