import unittest
from finance_analyzer import GermanBankParser, FinanceAnalyzer
import pandas as pd

class TestFinanceParser(unittest.TestCase):
    def test_german_float_conversion(self):
        self.assertEqual(GermanBankParser.parse_german_float('120,00'), 120.0)
        self.assertEqual(GermanBankParser.parse_german_float('1.250,50'), 1250.50)
        self.assertEqual(GermanBankParser.parse_german_float('- 120,00'), -120.0)
        self.assertEqual(GermanBankParser.parse_german_float('+50,00'), 50.0)
        self.assertIsNone(GermanBankParser.parse_german_float('invalid'))

    def test_categorize_basic(self):
        df = pd.DataFrame([
            {'Date': '01.01.2021', 'Description': 'Netflix subscription', 'Amount': -9.99},
            {'Date': '02.01.2021', 'Description': 'Salary payroll', 'Amount': 2500.0},
        ])
        analyzer = FinanceAnalyzer(df)
        analyzer.categorize()
        self.assertIn('Sub-Group', analyzer.df.columns)
        self.assertIn('Group', analyzer.df.columns)

if __name__ == '__main__':
    unittest.main()
