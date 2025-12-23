# Document Scanner with OCR, Lexicon + Regex Correlation - Setup Guide

## Project Overview
This is a complete document scanning system with OCR support and strict lexicon keyword detection correlated to regex patterns.

**Components:**
- `app.py` - Flask backend server
- `requirements.txt` - Python dependencies
- `index.html` - Web interface (frontend)
- `lexicon_latest.csv` - Strict multi-word keyword lexicon
- `regex_patterns.json` - Regex patterns used for correlation

---

## Installation & Setup

### Prerequisites
- Python 3.8+ installed
- Tesseract OCR installed on your system

### Step 1: Install Tesseract OCR

**Windows:**
1. Download installer: https://github.com/UB-Mannheim/tesseract/wiki
2. Run the installer (default path: `C:\Program Files\Tesseract-OCR`)
3. Update `app.py` line 6 with Tesseract path if needed:
```python
pytesseract.pytesseract.pytesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
```

**macOS:**
```bash
brew install tesseract
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get install tesseract-ocr
```

### Step 2: Install Python Dependencies

```bash
pip install -r requirements.txt
```

### Step 3: Run the Backend Server

```bash
python app.py
```

You should see:
```
Starting Document Scanner Backend Server...
Server running on http://localhost:5000
```

### Step 4: Open the Frontend

1. Save the HTML as `index.html` in your project folder
2. Open `index.html` in your web browser
3. The frontend will automatically connect to the backend at `http://localhost:5000`

---

## Usage

1. **Provide Documents**
   - Upload files via UI or API
   - Or scan a local path on the server using `path` + `recursive`
   - Supports: PDF, Word (.docx), Excel (.xlsx), JPEG, PNG, TIFF

2. **Configure Detection**
   - Keywords are loaded from `lexicon_latest.csv` by default
   - Regex patterns are loaded from `regex_patterns.json`
   - Only strict multi-word keywords are used from the lexicon

3. **Scan & Analyze** - Click to process documents

4. **Review Results**
   - Keyword hits are correlated to the nearest regex hit when both exist
   - Fallback mode returns standalone regex hits and keywords
   - Results include document, position, and context snippet

---

## File Descriptions

### app.py (Flask Backend)
Handles:
- File upload and validation
- Optional file collection from local path
- Text extraction from all document types
- OCR processing for images using Tesseract
- Strict lexicon keyword detection
- Regex pattern matching and proximity correlation
- Results compilation and JSON response

Key Functions:
- `extract_text_from_pdf()` - Handles text-based and scanned PDFs
- `extract_text_from_docx()` - Extracts from Word documents
- `extract_text_from_xlsx()` - Extracts from Excel files
- `extract_text_from_image()` - OCR processing using Tesseract
- `/scan` endpoint - Main API for document processing

### requirements.txt
Python packages:
- `pytesseract` - OCR interface
- `Pillow` - Image processing
- `PyPDF2` - PDF text extraction
- `python-docx` - Word document processing
- `openpyxl` - Excel processing
- `opencv-python` - Image manipulation
- `pdf2image` - PDF to image conversion
- `Flask` - Web server framework
 
### lexicon_latest.csv
Lexicon CSV containing keywords. Only strict multi-word, alphanumeric phrases are used.

### regex_patterns.json
JSON list of regex patterns with `name` and `pattern` used to find structured values.

---

## Advanced Configuration

### Change Backend URL
If running server on different port or host, edit HTML JavaScript:
```javascript
const API_BASE_URL = 'http://localhost:5000'; // Change this
```

### Increase Upload Limit
In `app.py`:
```python
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB
```

### Tesseract Language Support
By default uses English. For other languages, add to `app.py`:
```python
text = pytesseract.image_to_string(image, lang='deu')  # German
text = pytesseract.image_to_string(image, lang='fra')  # French
```

---

## Troubleshooting

**Problem: "Tesseract is not installed or not in PATH"**
- Solution: Install Tesseract (see Step 1) or update pytesseract path in app.py

**Problem: "Cannot connect to backend"**
- Ensure `python app.py` is running
- Check if using correct port (default: 5000)
- Verify firewall allows localhost:5000

**Problem: "File upload fails"**
- Check file size (default limit: 100MB)
- Verify file format is supported
- Check disk space in temp folder

**Problem: "OCR produces bad results"**
- Try preprocessing image (rotate, increase contrast)
- Use Tesseract language parameter
- Ensure image quality is good

---

## API Endpoints

### POST /scan
Scan documents and detect keywords

**Request:**
```
Content-Type: multipart/form-data

Parameters:
- files: (file array) Document files
- lexicon_path: (string) Optional path to lexicon CSV (default: lexicon_latest.csv)
- regex_path: (string) Optional path to regex JSON (default: regex_patterns.json)
- path: (string) Optional local path to scan on server
- recursive: (boolean) Scan path recursively (default: true)
- file_types: (string) Optional comma-separated extensions (e.g. "pdf,docx") to limit scans
- log_stdout: (boolean) Print progress/matches to stdout (default: true)
- log_path: (string) Optional log file path (append mode)
```

**Response:**
```json
{
  "success": true,
  "total_documents": 2,
  "documents_processed": ["file1.pdf", "file2.docx"],
  "total_matches": 5,
  "matches": [
    {
      "phrase": "invoice number",
      "document": "file1.pdf",
      "context": "...The invoice number is 12345...",
      "rejected": false,
      "position": 245
    }
  ],
  "errors": []
}
```

### GET /health
Check server status

**Response:**
```json
{
  "status": "Server is running",
  "ocr_available": true
}
```

### Run the API and test with curl

Start the server:
```bash
python app.py
```

Upload files directly:
```bash
curl -X POST http://localhost:5000/scan \
  -F "files=@/path/to/file1.pdf" \
  -F "files=@/path/to/file2.docx"
```

Scan a local directory on the server:
```bash
curl -X POST http://localhost:5000/scan \
  -F "path=/path/to/documents" \
  -F "recursive=true"
```

Scan only PDFs and DOCX files:
```bash
curl -X POST http://localhost:5000/scan \
  -F "path=/path/to/documents" \
  -F "file_types=pdf,docx"
```

Use a custom lexicon:
```bash
curl -X POST http://localhost:5000/scan \
  -F "lexicon_path=/path/to/custom_lexicon.csv" \
  -F "path=/path/to/documents"
```

Use a custom regex file:
```bash
curl -X POST http://localhost:5000/scan \
  -F "regex_path=/path/to/custom_regex.json" \
  -F "path=/path/to/documents"
```

Log matches to a file:
```bash
curl -X POST http://localhost:5000/scan \
  -F "path=/path/to/documents" \
  -F "log_path=/path/to/scan.log"
```

### Logging Output
Example lines when logging to stdout or a file:
```
matched_file: /path/to/documents/file1.pdf
match: keyword=invoice number document=/path/to/documents/file1.pdf nearest_regex=Date distance=12
match: regex=Email document=/path/to/documents/file2.docx value=jane@example.com
error: document=/path/to/documents/bad_file.pdf error=EOF marker not found
```

---

## Performance Tips

1. **Large Documents**: Process in batches for faster results
2. **OCR Speed**: Higher resolution images = slower OCR but better accuracy
3. **Keywords**: More keywords = longer processing time
4. **Caching**: Results are not cached; each scan re-processes

---

## Security Notes

- Files are temporarily stored in system temp folder and deleted after processing
- No files are permanently saved
- Maximum upload size: 100MB (configurable)
- CORS disabled by default (local use only)

For production use, add:
```python
from flask_cors import CORS
CORS(app)
```

---

## Support & Issues

- Check Tesseract is correctly installed
- Verify all Python packages are installed: `pip list`
- Check Python version: `python --version` (3.8+)
- Review Flask console output for error messages

Enjoy document scanning! 📄
