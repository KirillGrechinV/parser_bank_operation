import pandas as pd


class BankAnalyzer:
    "Класс для анализа: загрузка, очистка, статистика и экспорт."

    def __init__(self, file_bytes, filename):
        self.filename = filename
        self.raw_df = self._load_and_clean(file_bytes, filename)

        self.expenses = pd.DataFrame()
        self.income = pd.DataFrame()
        self.transit = pd.DataFrame()

        self.col_cat = 'Категория'  # значение по умолчанию
        for col in self.raw_df.columns:
            if 'категория' in col.lower():
                self.col_cat = col
                break
        self.col_desc = next((c for c in self.raw_df.columns if 'описание' in c.lower() or 'детали' in c.lower()),
                             'Описание')

    def _load_and_clean(self, file_bytes, filename):
        ext = filename.split('.')[-1].lower()
        if ext in ['xls', 'xlsx']:
            df = pd.read_excel(file_bytes)
        else:
            try:
                df = pd.read_csv(file_bytes, sep=';', encoding='utf-8')
            except UnicodeDecodeError:
                df = pd.read_csv(file_bytes, sep=';', encoding='cp1251')

        for i in range(min(15, len(df))):
            row_values = [str(val).lower() for val in df.iloc[i].values]
            joined_row = " ".join(row_values)
            if 'статус' in joined_row and 'сумма' in joined_row:
                df.columns = df.iloc[i].values
                df = df.iloc[i + 1:].reset_index(drop=True)
                break

        df.columns = [str(c).strip() for c in df.columns]
        return df

    def _clean_money(self, val):
        val_str = str(val).replace('\xa0', '').replace(' ', '').replace(',', '.')
        try:
            return float(val_str)
        except ValueError:
            return 0.0

    def process_data(self):
        df = self.raw_df.copy()

        col_status = next((c for c in df.columns if 'статус' in c.lower()), None)
        col_amount = next((c for c in df.columns if 'сумма' in c.lower()), None)

        if not col_status or not col_amount:
            raise ValueError("Не найдены колонки Статус или Сумма")

        valid_statuses = ['ok', 'ок', 'успешно']
        status_cleaned = df[col_status].astype(str).str.strip().str.lower()
        df = df[status_cleaned.isin(valid_statuses)]

        df['Сумма_чистая'] = df[col_amount].apply(self._clean_money)
        df = df[df['Сумма_чистая'] != 0].copy()

        if self.col_cat not in df.columns:
            df[self.col_cat] = 'Без категории'
        df[self.col_cat] = df[self.col_cat].fillna('Без категории')
        df[self.col_desc] = df[self.col_desc].fillna('Без описания')

        transit_words = ['перевод', 'себе', 'аноним']

        def is_transit(row):
            desc = str(row[self.col_desc]).lower()
            cat = str(row[self.col_cat]).lower()
            is_negative = row['Сумма_чистая'] < 0
            has_keyword = any(w in desc for w in transit_words) or 'перевод' in cat
            return is_negative and has_keyword

        transit_mask = df.apply(is_transit, axis=1)
        self.transit = df[transit_mask].copy()

        df_clean = df[~transit_mask].copy()
        self.expenses = df_clean[df_clean['Сумма_чистая'] < 0].copy()
        self.income = df_clean[df_clean['Сумма_чистая'] > 0].copy()

    def get_analytics(self):
        if self.expenses.empty:
            return None

        category_sums = self.expenses.groupby(self.col_cat)['Сумма_чистая'].sum().abs()
        top_5_expenses = self.expenses.sort_values(by='Сумма_чистая').head(5)
        avg_expense = abs(self.expenses['Сумма_чистая'].mean())

        return {
            "category_sums": category_sums,
            "top_5": top_5_expenses,
            "avg_expense": avg_expense
        }

    def generate_markdown_report(self):
        """Собирает готовый текст для импорта в Notion/Obsidian."""
        lines = ["# Финансовый отчет\n"]

        # Блок расходов
        lines.append("## Расходы")
        total_exp = 0
        if not self.expenses.empty:
            for cat, group in self.expenses.groupby(self.col_cat):
                lines.append(f"\n* **{cat}**")
                cat_sum = 0
                for _, row in group.iterrows():
                    amt = abs(row['Сумма_чистая'])
                    cat_sum += amt
                    lines.append(f"    * {row[self.col_desc]} - {amt:,.2f} руб")
                lines.append(f"    * **Итого по категории: {cat_sum:,.2f} руб**")
                total_exp += cat_sum
        lines.append(f"\n**ИТОГО ЧИСТЫЕ РАСХОДЫ: {total_exp:,.2f} руб**\n")

        # Блок доходов
        lines.append("## Поступления")
        total_inc = 0
        if not self.income.empty:
            for cat, group in self.income.groupby(self.col_cat):
                lines.append(f"\n* **{cat}**")
                cat_sum = 0
                for _, row in group.iterrows():
                    amt = abs(row['Сумма_чистая'])
                    cat_sum += amt
                    lines.append(f"    * {row[self.col_desc]} - {amt:,.2f} руб")
                lines.append(f"    * **Всего по категории: {cat_sum:,.2f} руб**")
                total_inc += cat_sum
        lines.append(f"\n**ИТОГО ПОСТУПЛЕНИЯ: {total_inc:,.2f} руб**")

        return "\n".join(lines)