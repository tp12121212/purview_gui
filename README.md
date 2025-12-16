# Document Scanner with OCR & Keyword Detection - Setup Guide

## Project Overview
This is a complete document scanning system with OCR support and intelligent keyword/phrase detection.

**Components:**
- `app.py` - Flask backend server
- `requirements.txt` - Python dependencies
- `index.html` - Web interface (frontend)

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

1. **Upload Documents** - Drag and drop or click to select files
   - Supports: PDF, Word (.docx), Excel (.xlsx), JPEG, PNG, TIFF

2. **Configure Detection**
   - Enter keywords to find (one per line)
   - Enter reject words/phrases to filter results
   - Choose detection mode:
     - **Phrase Detection**: Finds adjacent keywords exactly as typed
     - **Simple Keywords**: Finds individual keywords

3. **Set Options**
   - Case Sensitive: Match exact case
   - Whole Word Match: Only match complete words

4. **Scan & Analyze** - Click to process documents

5. **Review Results**
   - View matches with context
   - Rejected matches show with ⚠️ warning
   - Export as JSON or CSV

---

## File Descriptions

### app.py (Flask Backend)
Handles:
- File upload and validation
- Text extraction from all document types
- OCR processing for images using Tesseract
- Keyword phrase detection with filters
- Results compilation and JSON response

Key Functions:
- `extract_text_from_pdf()` - Handles text-based and scanned PDFs
- `extract_text_from_docx()` - Extracts from Word documents
- `extract_text_from_xlsx()` - Extracts from Excel files
- `extract_text_from_image()` - OCR processing using Tesseract
- `find_phrases()` - Intelligent keyword/phrase detection
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
- keywords: (string) Keywords separated by newlines
- reject_words: (string) Reject words separated by newlines
- case_sensitive: (boolean) Case sensitive matching
- whole_word: (boolean) Whole word matching
- mode: (string) 'phrase' or 'keyword'
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
