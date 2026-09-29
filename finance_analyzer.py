"""
Personal Finance Analyzer (v1.1.0)

Local workflow for German bank-statement PDFs:
Inbox -> validate -> MMM YYYY report folder -> Archive (success) / Error (failure).
Run unit tests separately with:  python -m unittest -v
"""
import pdfplumber
import pandas as pd
import matplotlib.pyplot as plt
import re
import shutil
from pathlib import Path
from datetime import datetime
import logging

# --- CONFIGURATION ---
# Personal paths and merchants live in config.py (ignored by Git).
# If config.py does not exist, safe defaults from config_example.py are used.
try:
    import config as _config
except ImportError:
    import config_example as _config

OUTPUT_ROOT = _config.OUTPUT_ROOT
INPUT_FOLDER = _config.INPUT_FOLDER
ARCHIVE_FOLDER = _config.ARCHIVE_FOLDER
ERROR_FOLDER = _config.ERROR_FOLDER
LOG_FOLDER = _config.LOG_FOLDER
DEBUG_PDF_TEXT = getattr(_config, "DEBUG_PDF_TEXT", False)
# Optional private merchant keywords, e.g. {"Dining": ["my local cafe"]}
EXTRA_CATEGORY_KEYWORDS = getattr(_config, "EXTRA_CATEGORY_KEYWORDS", {})

def setup_logging(log_folder, debug_pdf_text=False):
    """
    Creates a timestamped operational log for each run.

    Console output stays concise at INFO level.
    When debug_pdf_text is True, a separate DEBUG log is created for
    PDF text-extraction diagnostics. This may contain sensitive data.
    """
    log_folder = Path(log_folder)
    log_folder.mkdir(parents=True, exist_ok=True)

    run_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    normal_log_file = log_folder / (
        f"finance_analyzer_{run_timestamp}.log"
    )

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s"
    )

    # Normal operational log: INFO and above.
    file_handler = logging.FileHandler(
        normal_log_file,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Console: concise INFO and above.
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if debug_pdf_text:
        debug_log_file = log_folder / (
            f"finance_analyzer_debug_{run_timestamp}.log"
        )

        debug_handler = logging.FileHandler(
            debug_log_file,
            encoding="utf-8",
        )
        debug_handler.setLevel(logging.DEBUG)
        debug_handler.setFormatter(formatter)
        logger.addHandler(debug_handler)

        logging.warning(
            "PDF text diagnostic logging is enabled. "
            "The debug log may contain sensitive personal and financial data: %s",
            debug_log_file,
        )

    logging.info("Log file created: %s", normal_log_file)

    return normal_log_file


# --- OUTPUT FOLDER HELPERS ---

GERMAN_MONTHS = {
    "januar": 1,
    "februar": 2,
    "märz": 3,
    "maerz": 3,
    "april": 4,
    "mai": 5,
    "juni": 6,
    "juli": 7,
    "august": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "dezember": 12,
}

ENGLISH_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def get_pdf_header_text(filepath, max_pages=1):
    """
    Reads text from the first page, where bank-statement headers normally appear.
    Increase max_pages if your statement period sometimes appears later.
    """
    header_parts = []

    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages[:max_pages]:
            text = page.extract_text(x_tolerance=2)
            if text:
                header_parts.append(text)

    return "\n".join(header_parts)


def extract_statement_folder_name_from_text(header_text):
    """
    Returns the monthly folder name in MMM YYYY format.

    Detection priority:
    1. 'Kontoauszug vom DD.MM.YYYY bis DD.MM.YYYY'
    2. Any date range: 'DD.MM.YYYY bis DD.MM.YYYY'
    3. A numeric date: 'DD.MM.YYYY'
    4. A textual month/year: 'April 2023' or '28. April 2023'
    """
    if not header_text:
        return None

    # Normalize common PDF whitespace variants.
    normalized_text = (
        header_text
        .replace("\u00A0", " ")   # Non-breaking space
        .replace("\u2007", " ")   # Figure space
        .replace("\u202F", " ")   # Narrow non-breaking space
    )
    normalized_text = re.sub(r"\s+", " ", normalized_text).strip()

    # DD.MM.YYYY. The final dot after a year is allowed but not required.
    date_pattern = r"(\d{1,2})\s*\.\s*(\d{1,2})\s*\.\s*(\d{4})"

    # Priority 1:
    # Explicit standard bank-statement phrase.
    statement_period_pattern = (
        r"kontoauszug\s+vom\s+"
        + date_pattern
        + r"\s+bis\s+"
        + date_pattern
    )

    period_match = re.search(
        statement_period_pattern,
        normalized_text,
        flags=re.IGNORECASE,
    )

    # Priority 2:
    # Fallback if 'Kontoauszug vom' is omitted, split, reordered, or
    # extracted strangely but the date range itself remains available.
    if not period_match:
        date_range_pattern = (
            date_pattern
            + r"\s+bis\s+"
            + date_pattern
        )

        period_match = re.search(
            date_range_pattern,
            normalized_text,
            flags=re.IGNORECASE,
        )

    if period_match:
        try:
            # Groups 1–3: beginning date
            # Groups 4–6: end date
            end_day = int(period_match.group(4))
            end_month = int(period_match.group(5))
            end_year = int(period_match.group(6))

            return datetime(
                end_year,
                end_month,
                end_day,
            ).strftime("%b %Y")

        except ValueError:
            logging.warning(
                "Found a date range, but the end date was invalid: %s",
                period_match.group(0),
            )

    # Priority 3:
    # Any individual numeric date in the header.
    numeric_date_match = re.search(
        date_pattern,
        normalized_text,
        flags=re.IGNORECASE,
    )

    if numeric_date_match:
        try:
            day = int(numeric_date_match.group(1))
            month = int(numeric_date_match.group(2))
            year = int(numeric_date_match.group(3))

            return datetime(year, month, day).strftime("%b %Y")

        except ValueError:
            logging.warning(
                "Found a numeric date, but it was invalid: %s",
                numeric_date_match.group(0),
            )

    # Priority 4:
    # Textual month plus year, e.g. 'April 2023' or '28. April 2023'.
    months = {**GERMAN_MONTHS, **ENGLISH_MONTHS}

    month_names = "|".join(
        re.escape(month_name)
        for month_name in sorted(months.keys(), key=len, reverse=True)
    )

    month_year_match = re.search(
        rf"\b({month_names})\s+(\d{{4}})\b",
        normalized_text,
        flags=re.IGNORECASE,
    )

    if month_year_match:
        month_name = month_year_match.group(1).lower()
        year = int(month_year_match.group(2))

        return datetime(
            year,
            months[month_name],
            1,
        ).strftime("%b %Y")

    return None

def extract_statement_folder_name_from_filename(filepath):
    """
    Fallback for known historical statement filenames.

    Supported examples:
        DB_Bank_Stmt_Apr2023.pdf
        DB_Bank_Stmt_Aug2024.pdf
        statement-Apr2023.pdf
        Apr2023.pdf

    Returns:
        A value such as 'Apr 2023', or None if no valid supported
        month/year token occurs in the filename.
    """
    filename_stem = Path(filepath).stem

    month_abbreviations = {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }

    match = re.search(
        r"(?:^|[_\-\s])"
        r"("
        r"jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"
        r")"
        r"(\d{4})"
        r"(?:$|[_\-\s])",
        filename_stem,
        flags=re.IGNORECASE,
    )

    if not match:
        return None

    month_abbreviation = match.group(1).lower()
    year = int(match.group(2))
    month = month_abbreviations[month_abbreviation]

    return datetime(year, month, 1).strftime("%b %Y")


def extract_statement_folder_name(filepath):
    """
    Determines the report folder name.

    Priority:
    1. Read the statement period from the PDF header.
    2. Use the controlled historical filename convention as a fallback.
    """
    header_text = get_pdf_header_text(filepath)

    logging.debug(
        "Extracted first-page header text for %s:\n%s",
        filepath,
        header_text,
    )

    folder_name = extract_statement_folder_name_from_text(header_text)

    if folder_name:
        logging.info(
            "Statement period extracted from PDF header: %s",
            folder_name,
        )
        return folder_name

    folder_name = extract_statement_folder_name_from_filename(filepath)

    if folder_name:
        logging.warning(
            "Could not read a valid statement period from PDF text. "
            "Using controlled filename fallback for %s: %s",
            Path(filepath).name,
            folder_name,
        )
        return folder_name

    return None


def get_next_available_folder(base_folder):
    """
    Returns the first non-existing folder in this sequence:
    MMM YYYY[1], MMM YYYY[2], MMM YYYY[3], ...
    """
    counter = 1

    while True:
        candidate = base_folder.parent / f"{base_folder.name}[{counter}]"

        if not candidate.exists():
            return candidate

        counter += 1


def create_output_folder(pdf_file, output_root):
    """
    Creates and returns the monthly report folder for a bank statement.

    Returns:
        tuple[pathlib.Path | None, str]

        Status values:
        - "ready": Folder was successfully created or selected.
        - "cancelled": User intentionally chose Cancel.
        - "invalid_statement_header": No usable statement period was found.
    """
    folder_name = extract_statement_folder_name(pdf_file)

    if not folder_name:
        logging.error(
            "Could not extract a statement month/year from PDF header: %s",
            pdf_file,
        )

        print("\nERROR: Could not find a statement month and year in the PDF header.")
        print(
            "Expected a statement period such as:\n"
            "'Kontoauszug vom 01.08.2026 bis 31.08.2026'."
        )
        print("The PDF will be moved to the Error folder.")
        return None, "invalid_statement_header"

    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    target_folder = output_root / folder_name

    if target_folder.exists():
        print(f"\nOutput folder already exists:\n{target_folder}")
        logging.warning("Output folder already exists: %s", target_folder)

        while True:
            choice = input(
                "\nChoose an action: "
                "[O]verwrite, [C]ancel, or create [N]ew numbered folder: "
            ).strip().lower()

            if choice in ("o", "overwrite"):
                confirmation = input(
                    f"\nWARNING: This permanently deletes:\n{target_folder}\n"
                    "Type YES to confirm overwrite: "
                ).strip()

                if confirmation.upper() == "YES":
                    shutil.rmtree(target_folder)
                    target_folder.mkdir()

                    logging.info(
                        "Overwrote and recreated output folder: %s",
                        target_folder,
                    )

                    print(f"Created clean output folder:\n{target_folder}")
                    return target_folder, "ready"

                logging.info(
                    "Overwrite confirmation not received for: %s",
                    target_folder,
                )
                print("Overwrite was not confirmed. No files were deleted.")
                continue

            if choice in ("c", "cancel"):
                logging.info(
                    "User cancelled processing after existing output folder was found."
                )
                print("Operation cancelled. No output files were created.")
                return None, "cancelled"

            if choice in ("n", "new"):
                target_folder = get_next_available_folder(target_folder)
                target_folder.mkdir()

                logging.info(
                    "Created numbered output folder: %s",
                    target_folder,
                )

                print(f"Created new output folder:\n{target_folder}")
                return target_folder, "ready"

            print("Invalid choice. Enter O, C, or N.")

    target_folder.mkdir()

    logging.info("Created output folder: %s", target_folder)
    print(f"\nCreated output folder:\n{target_folder}")

    return target_folder, "ready"

def remove_empty_output_folder(output_dir):
    """
    Removes an output folder only when it is completely empty.

    This is safe for a newly created folder after a failed parse. It will
    never delete a folder that already contains reports or source files.
    """
    output_dir = Path(output_dir)

    if not output_dir.exists():
        return False

    if any(output_dir.iterdir()):
        logging.warning(
            "Output folder was not removed because it is not empty: %s",
            output_dir,
        )
        return False

    output_dir.rmdir()

    logging.info(
        "Removed empty output folder created before failed processing: %s",
        output_dir,
    )
    print(f"Removed empty output folder:\n{output_dir}")

    return True


def ensure_workflow_folders():
    """
    Ensures every configured workflow folder exists.
    """
    for folder in (
        INPUT_FOLDER,
        ARCHIVE_FOLDER,
        ERROR_FOLDER,
        LOG_FOLDER,
        OUTPUT_ROOT,
    ):
        folder.mkdir(parents=True, exist_ok=True)


def find_input_pdf(input_folder):
    """
    Selects exactly one PDF from the inbox.

    Rules:
    - Only files ending in .pdf are considered.
    - Temporary/browser-download files are ignored.
    - Exactly one PDF must be in the inbox.
    - More than one PDF is treated as an error to prevent processing
      the wrong statement.
    """
    input_folder = Path(input_folder)

    if not input_folder.exists():
        logging.error("Inbox folder does not exist: %s", input_folder)
        return None

    pdf_files = sorted(
        pdf_file
        for pdf_file in input_folder.iterdir()
        if (
            pdf_file.is_file()
            and pdf_file.suffix.lower() == ".pdf"
            and not pdf_file.name.startswith("~")
            and not pdf_file.name.endswith(".crdownload")
            and not pdf_file.name.endswith(".part")
            and not pdf_file.name.endswith(".tmp")
        )
    )

    if not pdf_files:
        logging.info("No PDF found in inbox: %s", input_folder)
        print(f"\nNo PDF found in inbox:\n{input_folder}")
        return None

    if len(pdf_files) > 1:
        logging.error(
            "Multiple PDFs found in inbox. Manual intervention required."
        )

        print(f"\nERROR: More than one PDF is in the inbox:\n{input_folder}")
        print("Keep only one bank-statement PDF in the inbox, then run again.")

        for pdf_file in pdf_files:
            logging.error("Inbox candidate: %s", pdf_file.name)
            print(f" - {pdf_file.name}")

        return None

    selected_pdf = pdf_files[0]
    logging.info("Selected input PDF: %s", selected_pdf)
    print(f"\nSelected input PDF:\n{selected_pdf}")

    return selected_pdf


def get_available_file_path(destination_folder, filename):
    """
    Returns an available path without overwriting an existing file.

    Example:
        statement.pdf
        statement[1].pdf
        statement[2].pdf
    """
    destination_folder = Path(destination_folder)
    source_name = Path(filename)

    candidate = destination_folder / source_name.name
    counter = 1

    while candidate.exists():
        candidate = destination_folder / (
            f"{source_name.stem}[{counter}]{source_name.suffix}"
        )
        counter += 1

    return candidate


def copy_source_pdf_to_report_folder(pdf_file, output_dir):
    """
    Copies the original input statement into the monthly report folder.

    The copy is named source_statement.pdf to make the report directory
    self-contained and easy to audit.
    """
    pdf_file = Path(pdf_file)
    output_dir = Path(output_dir)

    destination = output_dir / "source_statement.pdf"

    if destination.exists():
        destination = get_available_file_path(
            output_dir,
            "source_statement.pdf",
        )

    shutil.copy2(pdf_file, destination)

    logging.info("Copied source PDF to report folder: %s", destination)
    print(f"Source statement copied to:\n{destination}")

    return destination


def archive_input_pdf(pdf_file, archive_folder):
    """
    Moves a successfully processed input PDF from inbox to archive.

    If the original filename has already been archived, append [1], [2],
    and so on instead of overwriting an existing source document.
    """
    pdf_file = Path(pdf_file)
    archive_folder = Path(archive_folder)
    archive_folder.mkdir(parents=True, exist_ok=True)

    destination = get_available_file_path(archive_folder, pdf_file.name)

    shutil.move(str(pdf_file), str(destination))

    logging.info("Archived source PDF: %s", destination)
    print(f"Input PDF archived as:\n{destination}")

    return destination


def move_input_pdf_to_error(pdf_file, error_folder, reason):
    """
    Moves a failed input PDF from inbox to the error folder.

    A matching text file records why manual review is needed.
    """
    pdf_file = Path(pdf_file)
    error_folder = Path(error_folder)
    error_folder.mkdir(parents=True, exist_ok=True)

    destination = get_available_file_path(error_folder, pdf_file.name)

    shutil.move(str(pdf_file), str(destination))

    reason_file = destination.with_suffix(".error.txt")
    reason_file.write_text(
        f"Processing failed: {datetime.now():%Y-%m-%d %H:%M:%S}\n"
        f"Original file: {pdf_file.name}\n"
        f"Reason: {reason}\n",
        encoding="utf-8",
    )

    logging.error("Moved failed PDF to error folder: %s", destination)
    logging.error("Failure reason: %s", reason)

    print(f"\nPDF moved to error folder:\n{destination}")
    print(f"Reason recorded in:\n{reason_file}")

    return destination


def write_completion_marker(output_dir, pdf_file):
    """
    Creates a marker only after every output has been successfully created.
    """
    output_dir = Path(output_dir)
    pdf_file = Path(pdf_file)

    marker_file = output_dir / "processing_complete.txt"

    marker_file.write_text(
        f"Completed: {datetime.now():%Y-%m-%d %H:%M:%S}\n"
        f"Original PDF: {pdf_file.name}\n"
        f"Input location: {pdf_file}\n",
        encoding="utf-8",
    )

    logging.info("Completion marker written: %s", marker_file)
    return marker_file

# --- 1. DATA PROCESSING LOGIC ---


class GermanBankParser:
    def __init__(self, filepath):
        self.filepath = filepath

    @staticmethod
    def parse_german_float(value_str):
        if not value_str:
            return 0.0

        # Remove EUR symbol and spaces
        clean = value_str.replace("EUR", "").replace("€", "").replace(" ", "")

        # Handle signs
        factor = 1.0
        if "-" in clean:
            factor = -1.0
            clean = clean.replace("-", "")
        elif "+" in clean:
            clean = clean.replace("+", "")

        # German format: 1.000,00 -> remove dot, swap comma
        clean = clean.replace(".", "").replace(",", ".")

        try:
            return float(clean) * factor
        except ValueError:
            return 0.0

    def extract_data(self):
        print(f"Processing {self.filepath}...")
        transactions = []

        current_tx = None
        start_processing = False

        # 1. STOP TRIGGERS (End of Table indicators)
        stop_triggers = [
            "wichtige hinweise",
            "bic (swift)",
            "bic(swift)",
            "kontostand",
            "saldo",
            "neuer saldo",
            "übertrag",
            "einlagensicherungsgesetz",
            "zinsenfürdie",
        ]

        # Words to remove from description to keep it clean
        ignore_words = [
            "Verwendungszweck",
            "Kundenreferenz",
            "Mandatsreferenz",
            "Gläubiger-ID",
        ]

        with pdfplumber.open(self.filepath) as pdf:
            for page in pdf.pages:
                text = page.extract_text(x_tolerance=2)

                if not text:
                    continue

                lines = text.split("\n")

                for line in lines:
                    line_lower = line.lower()

                    # --- PHASE 1: SEARCH FOR HEADER ---
                    if not start_processing:
                        if "buchung" in line_lower and "valuta" in line_lower:
                            start_processing = True
                        continue

                    # --- PHASE 2: PROCESSING TRANSACTIONS ---

                    # Stop at footer / table-end markers
                    if any(trigger in line_lower for trigger in stop_triggers):
                        start_processing = False
                        break

                    # --- FIND ANCHOR (Amount) ---
                    amount_match = re.search(r"([+-]\s?[\d\.]+,\d{2})", line)

                    if amount_match:
                        # Save previous transaction
                        if current_tx:
                            transactions.append(current_tx)

                        raw_amount = amount_match.group(1)
                        amount = self.parse_german_float(raw_amount)

                        # Extract date (dd.mm.)
                        date_match = re.search(r"(\d{2}\.\d{2}\.)", line)
                        date = date_match.group(1) if date_match else ""

                        # Extract description
                        clean_desc = line.replace(raw_amount, " ").replace(date, " ").strip()

                        current_tx = {
                            "Date_Part": date,
                            "Year_Part": "",
                            "Description": clean_desc,
                            "Amount": amount,
                        }

                    elif current_tx:
                        # --- CONTINUATION LINES ---
                        year_match = re.search(r"^\s*(\d{4})\s", line)

                        if year_match and not current_tx["Year_Part"]:
                            current_tx["Year_Part"] = year_match.group(1)
                            line_content = line.replace(
                                year_match.group(1), " "
                            ).strip()
                            current_tx["Description"] += " " + line_content
                        else:
                            # Avoid page numbers within the table
                            if "seite" not in line_lower:
                                current_tx["Description"] += " " + line.strip()

        # Append final transaction
        if current_tx:
            transactions.append(current_tx)

        # Post-processing
        final_data = []

        for tx in transactions:
            full_date = f"{tx['Date_Part']}{tx['Year_Part']}"

            desc = tx["Description"]

            for word in ignore_words:
                desc = desc.replace(word, "")

            desc = re.sub(r"\s+", " ", desc).strip()

            final_data.append(
                {
                    "Date": full_date,
                    "Description": desc,
                    "Amount": tx["Amount"],
                }
            )

        self.df = pd.DataFrame(final_data)
        print(f"Extracted {len(self.df)} transactions.")
        return self.df

def percentage_label(pct, minimum_pct=3.0):
    """
    Return a percentage label only when the slice is large enough to read.

    Example:
        2.4% -> ""
        7.7% -> "7.7%"
    """
    return f"{pct:.1f}%" if pct >= minimum_pct else ""


def draw_readable_donut_chart(
    ax,
    values,
    title,
    colors=None,
    minimum_pct_label=3.0,
):
    """
    Draw a pie/doughnut chart with labels in an external legend.

    Parameters:
        ax: Matplotlib axis.
        values: Pandas Series whose index contains category names and whose
                values contain positive numeric totals.
        title: Chart title.
        colors: Optional color sequence.
        minimum_pct_label: Hide percentage text for smaller slices.
    """
    total = values.sum()

    if values.empty or total <= 0:
        ax.text(0.5, 0.5, "No data", ha="center", va="center")
        ax.set_title(title)
        ax.axis("off")
        return

    wedges, _, _ = ax.pie(
        values,
        labels=None,
        colors=colors,
        startangle=90,
        counterclock=False,
        autopct=lambda pct: percentage_label(pct, minimum_pct_label),
        pctdistance=0.72,
        wedgeprops={
            "width": 0.55,
            "edgecolor": "white",
            "linewidth": 1,
        },
        textprops={
            "fontsize": 9,
            "color": "black",
        },
    )

    legend_labels = [
        f"{category}: €{amount:,.2f} ({amount / total * 100:.1f}%)"
        for category, amount in values.items()
    ]

    ax.legend(
        wedges,
        legend_labels,
        title="Categories",
        loc="center left",
        bbox_to_anchor=(1.02, 0.5),
        fontsize=8,
        title_fontsize=9,
        frameon=False,
    )

    ax.set_title(title, fontsize=11, pad=14)
    ax.axis("equal")

def draw_income_summary_card(ax, income_sums):
    """
    Draws a compact KPI-style summary when income has only one category.

    A doughnut/pie chart is not meaningful when one category represents
    100% of the income total.
    """
    total_income = income_sums.sum()
    category_name = income_sums.index[0]
    category_amount = income_sums.iloc[0]

    ax.set_axis_off()

    ax.text(
        0.5,
        0.78,
        "Income",
        ha="center",
        va="center",
        fontsize=15,
        fontweight="bold",
        transform=ax.transAxes,
    )

    ax.text(
        0.5,
        0.52,
        f"€{total_income:,.2f}",
        ha="center",
        va="center",
        fontsize=23,
        fontweight="bold",
        color="#2ca02c",
        transform=ax.transAxes,
    )

    ax.text(
        0.5,
        0.32,
        category_name,
        ha="center",
        va="center",
        fontsize=11,
        wrap=True,
        transform=ax.transAxes,
    )

    ax.text(
        0.5,
        0.19,
        "100% of monthly income",
        ha="center",
        va="center",
        fontsize=9,
        color="dimgray",
        transform=ax.transAxes,
    )

    card = plt.Rectangle(
        (0.08, 0.08),
        0.84,
        0.82,
        fill=False,
        edgecolor="#2ca02c",
        linewidth=2,
        transform=ax.transAxes,
        clip_on=False,
    )

    ax.add_patch(card)

class FinanceAnalyzer:
    def __init__(self, df, output_dir, extra_keywords=None):
        self.df = df
        self.output_dir = Path(output_dir)

        # 1. CATEGORY DEFINITIONS
        # Generic German keywords. Matching is a lowercase substring check and
        # the FIRST matching category wins, so keep keywords specific.
        # Add your own merchants in config.py -> EXTRA_CATEGORY_KEYWORDS.
        self.categories = {
            "Rent Elec WiFi Mobile Gym Mortgage": [
                "miete", "wohnung", "tiefgarage", "nebenkosten", "hausverwaltung",
                "stadtwerke", "strom", "e.on", "vattenfall", "enbw",
                "telekom", "vodafone", "telefonica", "1&1",
                "fitness", "mcfit", "fitx", "urban sports",
                "darl.-leistung", "darlehen", "tilgung",
            ],
            "School & Education": [
                "schule", "kindergarten", "kita", "tuition",
                "universitaet", "hochschule", "volkshochschule", "musikschule",
                "nachhilfe", "udemy", "coursera", "linkedin learning",
            ],
            "Insurance": [
                "versicherung", "allianz", "huk-coburg", "krankenkasse",
                "techniker krankenkasse", "lebensvers", "haftpflicht",
            ],
            "Transport": [
                "db vertrieb", "db automaten", "deutsche bahn", "deutschlandticket",
                "mvv", "mvg", "bvg", "hvv", "vgn", "flixbus",
                "uber", "free now", "sixt", "share now",
                "tankstelle", "shell", "aral", "esso", "parkhaus", "parken",
            ],
            "Entertainment & Media": [
                "rundfunk", "beitragsservice", "netflix", "spotify", "prime video",
                "disney", "dazn", "youtube", "audible", "kino", "cinema",
            ],
            "Salary & Income": [
                "payroll", "salary", "gehalt", "lohn", "bezüge", "gutschrift",
                "rente", "erstattung", "familienkasse", "kindergeld", "finanzamt",
            ],
            "Dining": [
                "restaurant", "cafe", "bistro", "imbiss", "pizza", "doener",
                "baeckerei", "backstube", "backwerk", "kamps",
                "mcdonalds", "burger king", "subway", "starbucks",
                "vapiano", "nordsee", "lieferando", "wolt", "uber eats",
            ],
            "Groceries": [
                "rewe", "lidl", "aldi", "edeka", "kaufland", "penny", "netto",
                "dm drogerie", "dm-drogerie", "rossmann", "mueller",
                "alnatura", "denns", "metzgerei", "supermarkt", "asia markt",
            ],
            "Shopping": [
                "amazon", "paypal", "klarna", "zettle", "sumup",
                "zalando", "h&m", "zara", "primark", "ikea",
                "mediamarkt", "saturn", "apple", "google", "decathlon",
                "tchibo", "douglas", "shop", "store",
            ],
            "ATM Withdrawal": [
                "geldautomat", "bargeldauszahlung", "bargeldausz", "auszahlung gaa",
            ],
        }

        for category, keywords in (extra_keywords or {}).items():
            self.categories.setdefault(category, [])
            self.categories[category].extend(k.lower() for k in keywords)

        # 2. DEFINITION OF "FIXED" CATEGORIES
        self.always_fixed_categories = [
            "Rent Elec WiFi Mobile Gym Mortgage",
            "School & Education",
            "Insurance",
            "Entertainment & Media",
            "Groceries",
        ]

    def categorize(self):
        if self.df.empty:
            return

        def get_category(desc):
            desc_lower = str(desc).lower()

            for cat, keywords in self.categories.items():
                for keyword in keywords:
                    if keyword and keyword in desc_lower:
                        return cat

            if "lastschrift" in desc_lower or "sepa" in desc_lower:
                return "General Debit"

            return "Other"

        self.df["Sub-Group"] = self.df["Description"].apply(get_category)

        def get_expense_type(row):
            desc = row["Description"].lower()
            category = row["Sub-Group"]

            if (
                "dauerauftrag" in desc
                or "rcur" in desc
                or "wiederkehrend" in desc
            ):
                return "Fixed / Recurring"

            if category in self.always_fixed_categories:
                return "Fixed / Recurring"

            return "One-Time / Adhoc"

        self.df["Expense_Type"] = self.df.apply(get_expense_type, axis=1)
        self.df["Group"] = self.df["Amount"].apply(
            lambda amount: "Income" if amount > 0 else "Expenditure"
        )
        self.df["Abs_Amount"] = self.df["Amount"].abs()

    def generate_charts(self):
        if self.df.empty:
            print("No data to plot.")
            return

        fig, axes = plt.subplots(
            1,
            3,
            figsize=(27, 8),
            constrained_layout=True,
        )

        fig.suptitle(
            "Monthly Financial Report",
            fontsize=18,
            fontweight="bold",
        )

        # Chart 1: Income
        income_df = self.df[self.df["Group"] == "Income"]

        if not income_df.empty:
            income_sums = (
                income_df.groupby("Sub-Group")["Abs_Amount"]
                .sum()
                .sort_values(ascending=False)
            )

            if len(income_sums) == 1:
                draw_income_summary_card(axes[0], income_sums)
            else:
                draw_readable_donut_chart(
                    axes[0],
                    income_sums,
                    f"Income (€{income_sums.sum():,.2f})",
                    minimum_pct_label=3.0,
                )
        else:
            axes[0].text(
                0.5,
                0.5,
                "No Income",
                ha="center",
                va="center",
                fontsize=12,
            )
            axes[0].set_title("Income (€0.00)")
            axes[0].axis("off")

        # Chart 2: Spending by category
        expense_df = self.df[self.df["Group"] == "Expenditure"]

        if not expense_df.empty:
            category_sums = (
                expense_df.groupby("Sub-Group")["Abs_Amount"]
                .sum()
                .sort_values(ascending=False)
            )

            draw_readable_donut_chart(
                axes[1],
                category_sums,
                f"Spending by Category (€{category_sums.sum():,.2f})",
                minimum_pct_label=3.0,
            )

            # Chart 3: Fixed vs Adhoc costs
            type_sums = (
                expense_df.groupby("Expense_Type")["Abs_Amount"]
                .sum()
                .sort_values(ascending=False)
            )

            draw_readable_donut_chart(
                axes[2],
                type_sums,
                "Fixed vs. Adhoc Costs",
                colors=["#ff9999", "#66b3ff"],
                minimum_pct_label=0.0,
            )

        else:
            axes[1].text(
                0.5,
                0.5,
                "No Expenditure",
                ha="center",
                va="center",
            )
            axes[1].set_title("Spending by Category (€0.00)")
            axes[1].axis("off")

            axes[2].text(
                0.5,
                0.5,
                "No Expenditure",
                ha="center",
                va="center",
            )
            axes[2].set_title("Fixed vs. Adhoc Costs")
            axes[2].axis("off")

        chart_path = self.output_dir / "financial_report.png"

        fig.savefig(
            chart_path,
            dpi=300,
            bbox_inches="tight",
        )

        print(f"Report saved as:\n{chart_path}")

        plt.show()
        plt.close(fig)


# --- 3. MAIN EXECUTION ---


def main():
    """Run the Inbox -> report -> Archive/Error workflow once."""
    ensure_workflow_folders()
    setup_logging(
        LOG_FOLDER,
        debug_pdf_text=DEBUG_PDF_TEXT,
    )

    logging.info("Starting Personal Finance Analyzer.")
    pdf_file = find_input_pdf(INPUT_FOLDER)

    if pdf_file is None:
        logging.info("No eligible single input PDF available. Exiting.")
        return 0

    try:
        output_dir, folder_status = create_output_folder(pdf_file, OUTPUT_ROOT)

        if folder_status == "cancelled":
            logging.info("User cancelled processing. PDF remains in Inbox.")
            return 0

        if folder_status == "invalid_statement_header":
            reason = (
                "The PDF does not contain a recognizable bank-statement period. "
                "Expected wording similar to: "
                "'Kontoauszug vom 01.08.2026 bis 31.08.2026'."
            )

            move_input_pdf_to_error(
                pdf_file,
                ERROR_FOLDER,
                reason,
            )

            return 1

        if folder_status != "ready" or output_dir is None:
            raise RuntimeError(
                f"Unexpected output-folder status: {folder_status}"
            )

        parser = GermanBankParser(pdf_file)
        df = parser.extract_data()

        if df.empty:
            reason = (
                "No transactions were extracted. The 'Buchung' / 'Valuta' "
                "header may be missing, or the PDF format may have changed."
            )

            logging.error(reason)

            remove_empty_output_folder(output_dir)

            move_input_pdf_to_error(
                pdf_file,
                ERROR_FOLDER,
                reason,
            )

            return 1

        raw_csv_path = output_dir / "raw_transactions.csv"
        df.to_csv(raw_csv_path, index=False, encoding="utf-8-sig")
        logging.info("Raw transactions CSV saved: %s", raw_csv_path)
        print(f"Raw transactions saved as:\n{raw_csv_path}")

        analyzer = FinanceAnalyzer(
            df,
            output_dir,
            extra_keywords=EXTRA_CATEGORY_KEYWORDS,
        )
        analyzer.categorize()

        final_csv_path = output_dir / "final_report.csv"
        analyzer.df.to_csv(final_csv_path, index=False, encoding="utf-8-sig")
        logging.info("Final report CSV saved: %s", final_csv_path)
        print(f"Analysis complete. Final report saved as:\n{final_csv_path}")

        analyzer.generate_charts()

        chart_path = output_dir / "financial_report.png"

        if not chart_path.exists():
            raise RuntimeError(
                "Chart file was not created: financial_report.png"
            )

        copy_source_pdf_to_report_folder(pdf_file, output_dir)
        write_completion_marker(output_dir, pdf_file)
        archive_input_pdf(pdf_file, ARCHIVE_FOLDER)

        logging.info("Processing completed successfully.")
        print("\nSUCCESS: Processing completed and source PDF archived.")
        return 0

    except Exception as error:
        logging.exception("Unexpected processing error: %s", error)
        print(f"\nERROR: Processing failed: {error}")

        if pdf_file.exists():
            move_input_pdf_to_error(
                pdf_file,
                ERROR_FOLDER,
                f"Unexpected error: {error}",
            )

        return 1


if __name__ == "__main__":
    raise SystemExit(main())
