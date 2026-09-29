"""
Safe default configuration (committed to Git).

To use your own folders and merchants, copy this file to config.py and edit
config.py. config.py is listed in .gitignore, so it never reaches GitHub.
"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

INPUT_FOLDER = PROJECT_ROOT / "inbox"
ARCHIVE_FOLDER = PROJECT_ROOT / "archive"
ERROR_FOLDER = PROJECT_ROOT / "error"
LOG_FOLDER = PROJECT_ROOT / "logs"

# Parent folder in which the MMM YYYY report folders are created.
OUTPUT_ROOT = PROJECT_ROOT / "output"

# True only while diagnosing PDF text extraction.
# Debug logs can contain names, addresses, IBANs and transactions.
DEBUG_PDF_TEXT = False

# Optional: your own merchants, added to the built-in category keywords.
# Keep personal merchants in config.py only, for example:
# EXTRA_CATEGORY_KEYWORDS = {
#     "Dining": ["my favourite cafe"],
#     "School & Education": ["my kids school"],
#     "ATM Withdrawal": ["nr12345678"],
# }
EXTRA_CATEGORY_KEYWORDS = {}
