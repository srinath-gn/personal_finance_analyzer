# personal_finance_analyzer

Brief description
-----------------
PErsonal Finance Analyzer is a small CLI tool to parse German bank statement PDFs, extract transactions, categorize income and spending, and generate a simple monthly financial report (CSV + chart image).

Key features
------------
- Parse German-formatted monetary values and extract transactions from PDF bank statements using `pdfplumber`.
- Categorize transactions into user-friendly groups and flag recurring vs one-time expenses.
- Produce a cleaned CSV (`final_report.csv`) and a visual report image (`financial_report.png`).
- Headless plotting support for CI or servers (use `--no-show`).

Requirements
------------
- Python 3.8+
- `pandas`, `pdfplumber`, `matplotlib`
- See `requirements.txt` for exact pins.

Quick usage
-----------
Run the analyzer on a German bank statement PDF:

python finance_analyzer.py /path/to/bank_statement.pdf --out-dir out --save-raw-csv

Options
-------
- `--out-dir`: directory to write `final_report.csv`, `raw_transactions.csv` (if requested), and `financial_report.png`.
- `--no-show`: do not open plot interactively (useful on headless machines).
- `--save-raw-csv`: save parsed raw transactions before categorization.

Outputs
-------
- `final_report.csv`: categorized transactions and added metadata columns.
- `raw_transactions.csv` (optional): initially extracted transaction rows.
- `financial_report.png`: pie-chart summary for income, spending by category, and fixed vs adhoc costs.

Notes
-----
- The parser is tuned for German formatting (e.g., '1.234,56' currency strings) and typical PDF layout from Deutsche Bank; results may vary with other formats.
- If no transactions are extracted, check the PDF layout and header detection.

License / Attribution
---------------------
This is a small personal utility; adapt and extend as needed.

