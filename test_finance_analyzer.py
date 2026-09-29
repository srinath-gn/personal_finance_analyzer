import tempfile
import unittest
from pathlib import Path

import pandas as pd

from finance_analyzer import (
    FinanceAnalyzer,
    GermanBankParser,
    extract_statement_folder_name_from_filename,
    extract_statement_folder_name_from_text,
    get_available_file_path,
)


def categorize(rows, extra_keywords=None):
    df = pd.DataFrame(rows)
    with tempfile.TemporaryDirectory() as temp_dir:
        analyzer = FinanceAnalyzer(df, temp_dir, extra_keywords=extra_keywords)
        analyzer.categorize()
    return analyzer.df


class TestGermanFloat(unittest.TestCase):
    def test_german_float_conversion(self):
        self.assertEqual(GermanBankParser.parse_german_float("120,00"), 120.0)
        self.assertEqual(GermanBankParser.parse_german_float("1.250,50"), 1250.50)
        self.assertEqual(GermanBankParser.parse_german_float("- 120,00"), -120.0)
        self.assertEqual(GermanBankParser.parse_german_float("+ 50,00"), 50.0)


class TestStatementPeriod(unittest.TestCase):
    def test_folder_name_from_bank_header(self):
        header = """
        31. August 2026
        Kontoauszug vom 01.08.2026 bis 31.08.2026
        """
        self.assertEqual(extract_statement_folder_name_from_text(header), "Aug 2026")

    def test_folder_name_april_2023(self):
        header = """
        28. April 2023
        Kontoauszug vom 01.04.2023 bis 28.04.2023
        """
        self.assertEqual(extract_statement_folder_name_from_text(header), "Apr 2023")

    def test_folder_name_uses_end_date_across_year_boundary(self):
        header = "Kontoauszug vom 30.12.2023 bis 31.01.2024"
        self.assertEqual(extract_statement_folder_name_from_text(header), "Jan 2024")

    def test_folder_name_with_split_date_range(self):
        header = """
        Kontoauszug vom
        01.04.2023
        bis
        28.04.2023
        """
        self.assertEqual(extract_statement_folder_name_from_text(header), "Apr 2023")

    def test_invalid_header_returns_none(self):
        header = """
        The New Software Development Game
        A talk about software delivery and organizational learning.
        """
        self.assertIsNone(extract_statement_folder_name_from_text(header))

    def test_folder_name_from_historical_filename(self):
        self.assertEqual(
            extract_statement_folder_name_from_filename("DB_Bank_Stmt_Apr2023.pdf"),
            "Apr 2023",
        )

    def test_invalid_filename_returns_none(self):
        self.assertIsNone(
            extract_statement_folder_name_from_filename(
                "The New Software Development Game.pdf"
            )
        )


class TestFileHelpers(unittest.TestCase):
    def test_available_path_uses_original_name_when_free(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            self.assertEqual(
                get_available_file_path(folder, "statement.pdf"),
                folder / "statement.pdf",
            )

    def test_available_path_adds_number_when_file_exists(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            (folder / "statement.pdf").touch()
            (folder / "statement[1].pdf").touch()
            self.assertEqual(
                get_available_file_path(folder, "statement.pdf"),
                folder / "statement[2].pdf",
            )


class TestCategorization(unittest.TestCase):
    def test_categorize_basic(self):
        df = categorize(
            [
                {"Date": "01.01.2024", "Description": "Netflix subscription", "Amount": -9.99},
                {"Date": "02.01.2024", "Description": "Gehalt Januar", "Amount": 2500.0},
            ]
        )
        self.assertEqual(df.loc[0, "Sub-Group"], "Entertainment & Media")
        self.assertEqual(df.loc[0, "Group"], "Expenditure")
        self.assertEqual(df.loc[1, "Sub-Group"], "Salary & Income")
        self.assertEqual(df.loc[1, "Group"], "Income")

    def test_mediamarkt_is_shopping_not_groceries(self):
        df = categorize([{"Date": "05.01.2024", "Description": "MediaMarkt Online", "Amount": -99.0}])
        self.assertEqual(df.loc[0, "Sub-Group"], "Shopping")

    def test_mastercard_is_not_entertainment(self):
        df = categorize([{"Date": "06.01.2024", "Description": "Mastercard Abrechnung", "Amount": -50.0}])
        self.assertNotEqual(df.loc[0, "Sub-Group"], "Entertainment & Media")

    def test_extra_keywords_from_config(self):
        df = categorize(
            [{"Date": "07.01.2024", "Description": "Kartenzahlung Local Bakery XY", "Amount": -3.2}],
            extra_keywords={"Dining": ["Local Bakery XY"]},
        )
        self.assertEqual(df.loc[0, "Sub-Group"], "Dining")


if __name__ == "__main__":
    unittest.main()
