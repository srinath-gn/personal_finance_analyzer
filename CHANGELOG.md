# Changelog

## [1.1.0] - 2026-09-29

### Added
- Inbox, Archive, Error and Logs workflow; no more renaming files to `statement.pdf`
- Checks that exactly one PDF is in Inbox; refuses to guess when there are several
- Monthly `MMM YYYY` report folders based on the statement period in the PDF header
- Filename fallback for older files named like `DB_Bank_Stmt_Apr2023.pdf`
- Choice to overwrite, cancel or create a numbered folder when a month already exists
- Copy of the source statement and a `processing_complete.txt` marker in each report folder
- Source PDF moved to Archive only after a fully successful run
- Failed PDFs moved to Error with a `.error.txt` reason file; empty report folders removed
- Timestamped log for each run; optional debug log for PDF text, off by default
- Doughnut charts with an external legend; summary card when there is only one income category
- More unit tests (statement period, filename fallback, file naming, categorization)
- `config_example.py` so personal paths stay in an ignored `config.py`

### Changed
- The script now runs with no arguments and reads from Inbox instead of taking a PDF path
- Unit tests run separately with `python -m unittest -v`

### Known limitations
- PDFs must contain selectable text; scanned statements are not supported
- Some older PDFs have a corrupted text layer and are rejected to Error
- Categorization uses keyword matching

## [1.0.0]
- First CLI version: PDF parsing, categorization, CSV and chart output
