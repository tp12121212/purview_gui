#!/usr/bin/env bash
set -e

echo "=== Document Scanner setup for macOS ==="

# ---- 1. Check Homebrew ----
if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is not installed."
  echo "Install it from https://brew.sh and re-run this script."
  exit 1
fi

# ---- 2. Install OS-level dependencies ----
echo "Installing Tesseract OCR and Poppler (for pdf2image)..."
brew update
brew install tesseract poppler

# ---- 3. Create Python virtual environment ----
PYTHON_BIN=${PYTHON_BIN:-python3.11}
VENV_DIR=${VENV_DIR:-.venv}

echo "Creating virtual environment in '${VENV_DIR}' using '${PYTHON_BIN}'..."
$PYTHON_BIN -m venv "$VENV_DIR"

echo "Activating virtual environment..."
# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

# ---- 4. Upgrade pip ----
echo "Upgrading pip..."
pip install --upgrade pip

# ---- 5. Install Python dependencies ----
if [ -f "requirements.txt" ]; then
  echo "Installing Python packages from requirements.txt..."
  pip install -r requirements.txt
else
  echo "requirements.txt not found. Installing core deps directly..."
  pip install flask pytesseract pillow PyPDF2 pycryptodome python-docx openpyxl opencv-python pdf2image regex
fi

# ---- 6. Final info ----
echo
echo "=== Setup complete ==="
echo "Virtual environment: $VENV_DIR"
echo "To activate it in a new terminal, run:"
echo "  source $VENV_DIR/bin/activate"
echo
echo "To start the backend:"
echo "  source $VENV_DIR/bin/activate"
echo "  python app.py"
