"""
Improved finance analyzer module.
- CLI via argparse
- logging instead of prints
- flexible amount/date parsing
- optional headless plotting
- safer error handling
"""
from __future__ import annotations

import argparse
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import pandas as pd


# Only import plotting when needed to keep headless/CI friendly
@dataclass
class GermanBankParser:
    filepath: Path

    @staticmethod
    def parse_german_float(value_str: Optional[str]) -> Optional[float]:
        """Convert German formatted monetary string to float.
        Examples: '1.234,56', '- 120,00', '+50,00', '120,00'
        Returns None on invalid input.
        """
        if value_str is None:
            return None

        s = str(value_str).strip()
        if not s:
            return None

        # Remove currency symbols and whitespace
        s = s.replace('EUR', '').replace('€', '').replace('\u202f', '').strip()

        # Capture optional sign
        match = re.match(r'^([+-])?\s*([\d\.]+,\d{2})$', s)
        if not match:
            # try a more permissive approach: allow numbers without thousands separators
            match2 = re.match(r'^([+-])?\s*([\d]+,\d{2})$', s)
            if not match2:
                logging.debug("parse_german_float: couldn't match pattern for '%s'", value_str)
                return None
            sign, num = match2.groups()
        else:
            sign, num = match.groups()

        # normalize: remove thousands '.' and replace decimal ',' with '.'
        num = num.replace('.', '').replace(',', '.')
        try:
            val = float(num)
        except ValueError:
            logging.exception("parse_german_float: failed to parse number part '%s'", num)
            return None

        if sign == '-':
            val = -val
        return val

    def extract_data(self) -> pd.DataFrame:
        import pdfplumber

        logging.info('Processing %s', self.filepath)
        transactions: List[dict] = []

        current_tx = None
        start_processing = False

        stop_triggers = [
            'wichtige hinweise', 'bic (swift)', 'bic(swift)', 'kontostand', 'saldo', 'neuer saldo',
            'übertrag', 'einlagensicherungsgesetz', 'zinsenfürdie'
        ]

        ignore_words = ['Verwendungszweck', 'Kundenreferenz', 'Mandatsreferenz', 'Gläubiger-ID']

        amount_re = re.compile(r'([+-]\s?[\d\.]+,\d{2})')
        date_re = re.compile(r'(\d{2}\.\d{2}\.)')
        year_re = re.compile(r'^\s*(\d{4})\s')

        with pdfplumber.open(self.filepath) as pdf:
            for page in pdf.pages:
                text = page.extract_text(x_tolerance=2)
                if not text:
                    continue
                lines = text.split('\n')
                for line in lines:
                    line_lower = line.lower()
                    if not start_processing:
                        if 'buchung' in line_lower and 'valuta' in line_lower:
                            start_processing = True
                        continue

                    if any(trigger in line_lower for trigger in stop_triggers):
                        start_processing = False
                        break

                    m = amount_re.search(line)
                    if m:
                        if current_tx:
                            transactions.append(current_tx)

                        raw_amount = m.group(1)
                        amount = self.parse_german_float(raw_amount)
                        date_match = date_re.search(line)
                        date_part = date_match.group(1) if date_match else ''
                        clean_desc = line.replace(raw_amount, ' ').replace(date_part, ' ').strip()

                        current_tx = {
                            'Date_Part': date_part,
                            'Year_Part': '',
                            'Description': clean_desc,
                            'Amount': amount if amount is not None else 0.0,
                            'Raw_Amount': raw_amount,
                        }
                    elif current_tx:
                        y = year_re.search(line)
                        if y and not current_tx['Year_Part']:
                            current_tx['Year_Part'] = y.group(1)
                            line_content = line.replace(y.group(1), ' ').strip()
                            current_tx['Description'] += ' ' + line_content
                        else:
                            if 'seite' not in line_lower:
                                current_tx['Description'] += ' ' + line.strip()

        if current_tx:
            transactions.append(current_tx)

        final_data = []
        for tx in transactions:
            full_date = f"{tx['Date_Part']}{tx['Year_Part']}".strip()
            desc = tx['Description']
            for w in ignore_words:
                desc = desc.replace(w, '')
            desc = re.sub(r'\s+', ' ', desc).strip()
            final_data.append({'Date': full_date, 'Description': desc, 'Amount': tx['Amount']})

        df = pd.DataFrame(final_data)
        logging.info('Extracted %d transactions', len(df))
        return df


class FinanceAnalyzer:
    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
        self.categories = {
            'Rent Elec WiFi Mobile Gym Mortgage': [
                'miete', 'wohnung', 'stadtwerke', 'strom', 'sueW', 'Telek', 'training', 'sport', 'hausverwaltung', 'Darl.-Leistung', 'Zinsen'
            ],
            'School & Education': ['schule', 'kita', 'tuition'],
            'Insurance': ['versicherung', 'allianz', 'krankenkasse'],
            'Transport': ['mvg', 'deutsche bahn', 'uber', 'tankstelle', 'parken'],
            'Entertainment & Media': ['netflix', 'spotify', 'prime video', 'kino'],
            'Salary & Income': ['payroll', 'salary', 'lohn', 'gehalt'],
            'Dining': ['restaurant', 'cafe', 'baeckerei', 'bistro', 'backstube'],
            'Groceries': ['rewe', 'lidl', 'aldi', 'edeka', 'DM-Drogerie'],
            'Shopping': ['amazon', 'paypal', 'zalando', 'ikea', 'h&m', 'mediamarkt', 'saturn','tchibo']
        }
        self.always_fixed_categories = [
            'Rent Elec WiFi Mobile Gym Mortgage', 'School & Education', 'Insurance', 'Entertainment & Media', 'Groceries'
        ]

    def categorize(self) -> None:
        if self.df.empty:
            logging.warning('Empty dataframe passed to FinanceAnalyzer.categorize')
            return

        def get_category(desc: str) -> str:
            desc_lower = str(desc).lower()
            for cat, keywords in self.categories.items():
                for k in keywords:
                    if k and re.search(rf'\b{re.escape(k)}\b', desc_lower):
                        return cat
            if 'lastschrift' in desc_lower or 'sepa' in desc_lower:
                return 'General Debit'
            return 'Other'

        self.df['Sub-Group'] = self.df['Description'].apply(get_category)

        def get_expense_type(row) -> str:
            desc = str(row['Description']).lower()
            category = row['Sub-Group']
            if 'dauerauftrag' in desc or 'rcur' in desc or 'wiederkehrend' in desc:
                return 'Fixed / Recurring'
            if category in self.always_fixed_categories:
                return 'Fixed / Recurring'
            return 'One-Time / Adhoc'

        self.df['Expense_Type'] = self.df.apply(get_expense_type, axis=1)
        self.df['Group'] = self.df['Amount'].apply(lambda x: 'Income' if x > 0 else 'Expenditure')
        self.df['Abs_Amount'] = self.df['Amount'].abs()

    def generate_charts(self, out_path: Path | str = 'financial_report.png', show: bool = True) -> None:
        import matplotlib
        if not show:
            matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        if self.df.empty:
            logging.info('No data to plot.')
            return

        fig, axes = plt.subplots(1, 3, figsize=(20, 7))
        fig.suptitle('Monthly Financial Report', fontsize=18)

        income_df = self.df[self.df['Group'] == 'Income']
        if not income_df.empty:
            income_sums = income_df.groupby('Sub-Group')['Abs_Amount'].sum()
            axes[0].pie(income_sums, labels=income_sums.index, autopct='%1.1f%%', startangle=140)
            axes[0].set_title(f"Income (€{income_sums.sum():.2f})")
        else:
            axes[0].text(0.5, 0.5, 'No Income', ha='center')

        expense_df = self.df[self.df['Group'] == 'Expenditure']
        if not expense_df.empty:
            cat_sums = expense_df.groupby('Sub-Group')['Abs_Amount'].sum()
            axes[1].pie(cat_sums, labels=cat_sums.index, autopct='%1.1f%%', startangle=140)
            axes[1].set_title(f"Spending by Category (€{cat_sums.sum():.2f})")

            type_sums = expense_df.groupby('Expense_Type')['Abs_Amount'].sum()
            axes[2].pie(type_sums, labels=type_sums.index, autopct='%1.1f%%', startangle=140, colors=['#ff9999', '#66b3ff'])
            axes[2].set_title('Fixed vs. Adhoc Costs')

        plt.tight_layout()
        plt.savefig(out_path, dpi=300)
        logging.info('Report saved as %s', out_path)
        if show:
            plt.show()


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Parse German bank statement PDFs and analyze transactions')
    parser.add_argument('input', type=Path, help='Path to the PDF bank statement')
    parser.add_argument('--out-dir', type=Path, default=Path('.'), help='Output directory')
    parser.add_argument('--no-show', action='store_true', help='Do not show plots interactively')
    parser.add_argument('--save-raw-csv', action='store_true', help='Save raw_transactions.csv')

    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    if not args.input.exists():
        logging.error('Input file not found: %s', args.input)
        return 2

    parser_obj = GermanBankParser(args.input)
    df = parser_obj.extract_data()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    if args.save_raw_csv:
        df.to_csv(args.out_dir / 'raw_transactions.csv', index=False)

    if df.empty:
        logging.error('No transactions extracted. Check the PDF format and header detection.')
        return 3

    analyzer = FinanceAnalyzer(df)
    analyzer.categorize()
    analyzer.df.to_csv(args.out_dir / 'final_report.csv', index=False)
    analyzer.generate_charts(args.out_dir / 'financial_report.png', show=not args.no_show)
    logging.info('Analysis complete. Outputs written to %s', args.out_dir)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
