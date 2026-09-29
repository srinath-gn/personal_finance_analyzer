# 🇩🇪 German Personal Finance Analyzer

Turn German bank-statement PDFs into monthly financial reports on your own computer. The tool reads a statement, extracts and categorizes the transactions, and creates CSV files and a chart. Your financial data never leaves your computer.

> [!WARNING]
> Bank statements, reports, logs and `config.py` contain personal data. They are excluded by `.gitignore`. Never commit them.

## How it works

```text
Download statement PDF → put it in inbox/ → run the script → open the report folder
```

For the one PDF in `inbox/`, the script:

1. Finds the statement period in the header, for example `Kontoauszug vom 01.08.2026 bis 31.08.2026`
2. Creates a report folder named after the end date, for example `Aug 2026`
3. Extracts and categorizes the transactions
4. Saves the CSV files, the chart, a copy of the PDF and a completion marker
5. Moves the original PDF to `archive/`

If something goes wrong, the PDF goes to `error/` with a `.error.txt` file explaining why.

## Requirements

- Python 3.10 or later
- A text-based (not scanned) German bank-statement PDF. It is tuned for the Deutsche Bank layout.

## Installation

```powershell
git clone https://github.com/srinath-gn/personal_finance_analyzer.git
cd personal_finance_analyzer
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Configuration (optional)

By default, the script uses the `inbox/`, `archive/`, `error/` and `logs/` folders in the project, and writes reports to `output/`.

To use other folders, copy the example file and edit your copy:

```powershell
Copy-Item config_example.py config.py
```

`config.py` is ignored by Git, so your personal paths stay private.

## Usage

1. Put exactly one statement PDF in `inbox/`. You don't need to rename it.
2. Run:

   ```powershell
   python finance_analyzer.py
   ```

3. Open the new report folder, for example `output/Aug 2026/`.

If the month's folder already exists, the script asks you to choose: **O** to overwrite (you then type `YES`), **C** to cancel, or **N** to create `Aug 2026[1]`, `Aug 2026[2]` and so on.

## Output

| File | Contents |
|---|---|
| `raw_transactions.csv` | Transactions as extracted from the PDF |
| `final_report.csv` | Transactions with category, income/expenditure and fixed/one-time type |
| `financial_report.png` | Income, spending by category, and fixed vs. one-time costs |
| `source_statement.pdf` | Copy of the input statement |
| `processing_complete.txt` | Written only when the whole run succeeds |

## Behaviour summary

| Situation | Result |
|---|---|
| Inbox is empty | Exits with a message |
| More than one PDF in Inbox | Lists the files and exits; nothing is moved |
| No statement period found | PDF moved to `error/` |
| No transactions extracted | PDF moved to `error/`; empty report folder removed |
| Success | PDF moved to `archive/` |

Each run writes a timestamped log to `logs/`. To see the raw PDF text while troubleshooting, set `DEBUG_PDF_TEXT = True` in `config.py`. This writes a separate debug log that contains personal data. Switch it off again afterwards.

## Tests

```powershell
python -m unittest -v
```

## Customising categories

Categories are keyword lists in `FinanceAnalyzer.categories` in `finance_analyzer.py`. The first category with a matching keyword wins. Add your own merchants to improve the results.

## Limitations

- Scanned (image-only) PDFs are not supported.
- Some older PDFs have a corrupted text layer. These are safely moved to `error/`.
- Other banks' layouts may need parser changes.

See `CHANGELOG.md` for the version history.

## License

MIT, see `LICENSE`.
