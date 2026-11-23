import pandas as pd


class BankAnalyzer:
    """Класс для анализа выписки: загрузка, очистка, статистика и экспорт."""

    def __init__(self, file_bytes, filename):
        self.filename = filename
        self.raw_df = self._load_and_clean(file_bytes, filename)

        # Заранее создаем пустые таблицы, чтобы они существовали еще до запуска обработки
        self.expenses = pd.DataFrame()
        self.income = pd.DataFrame()
        self.transit = pd.DataFrame()

        # Реальные названия нужных колонок в загруженной выписке
        self.col_cat = self._find_column(self.raw_df.columns, ['категория'], default='Категория')
        self.col_desc = self._find_column(self.raw_df.columns, ['описание', 'детали'], default='Описание')

    def _find_column(self, columns, keywords, default=None):
        # В выписках может смениться название колонок, поэтому учтем это
        # поэтому ищем подходящую колонку по ключевым словам без учета регистра
        for col in columns:
            col_lower = col.lower()
            for word in keywords:
                if word in col_lower:
                    return col
        return default

    def _load_and_clean(self, file_bytes, filename):
        df = self._read_raw_file(file_bytes, filename)
        df = self._fix_table_header(df)

        # на всякий случай убираем случайные пробелы по краям названий колонок, чтобы они не мешали поиску,
        clean_columns = []
        for col in df.columns:
            clean_columns.append(str(col).strip()) # <- str не убирать, ошибка чтения будет
        df.columns = clean_columns

        return df

    def _read_raw_file(self, file_bytes, filename):
        ext = filename.split('.')[-1].lower() # <- разбиваем файл для понимания формата, .lower() если будет CSV, XLSX и т.д. а не csv и т.д.

        if ext in ['xls', 'xlsx']:
            return pd.read_excel(file_bytes) # <- читает только олин лист по дефолту

        # Выписки в CSV могут быть cp1251,
        # поэтому сначала пробуем стандартный utf-8, а при ошибке - на cp1251
        try:
            return pd.read_csv(file_bytes, sep=';', encoding='utf-8')
        except UnicodeDecodeError:
            # После неудачной попытки чтения возвращаем курсор файла в начало
            if hasattr(file_bytes, 'seek'):
                file_bytes.seek(0) # <- seek(0) не убирать, может начать парсить не с нуля
            return pd.read_csv(file_bytes, sep=';', encoding='cp1251')

    def _fix_table_header(self, df):
        # В выписках первые строки могут быть заняты служебной шапкой (название банка, номер счета, период). Поэтому подготовим
        rows_to_check = min(15, len(df)) # Просматриваем первые 15 строк в поисках реальных заголовков таблицы.

        for i in range(rows_to_check):
            row_words = []
            for val in df.iloc[i].values:
                row_words.append(str(val).lower()) # <- str не убирать, ошибка чтения будет

            joined_row = " ".join(row_words)
            if 'статус' in joined_row and 'сумма' in joined_row: # ищем сразу два слова, чтобы не спутать со служебной строкой шапки, где есть только слово "сумма"
                # Ставим найденную строку как заголовки колонок и отбрасываем всё, что было выше неё
                df.columns = df.iloc[i].values # <- .values возвращает массив
                df = df.iloc[i + 1:].reset_index(drop=True) # drop=True удаляет старый индекс
                break

        return df
    def _clean_money(self, val):
        val_str = str(val).replace('\xa0', '').replace(' ', '').replace(',', '.') # \xa0 — неразрывный пробел
        try:
            return float(val_str)
        except ValueError:
            return 0.0

    def _is_transit_operation(self, row):
        # Транзитными переводами (например, переводы себе) считаем только списания
        if row['Сумма_чистая'] >= 0:
            return False

        cat = str(row[self.col_cat]).lower()
        if 'перевод' in cat:
            return True

        desc = str(row[self.col_desc]).lower()
        transit_words = ['перевод', 'себе', 'аноним']
        for word in transit_words:
            if word in desc:
                return True

        return False

    def process_data(self):
        df = self.raw_df.copy() # <- через copy() новая таблица, сохраняем сырую таблицу

        # 1. Ищем обязательные колонки, без которых анализ невозможен
        col_status = self._find_column(df.columns, ['статус'])
        col_amount = self._find_column(df.columns, ['сумма'])
        if not col_status or not col_amount:
            raise ValueError("Не найдены колонки Статус или Сумма")

        # 2. Оставляем только успешные операции ('ok' — латиницей, 'ок' — кириллицей)
        valid_statuses = ['ok', 'ок', 'успешно']
        status_cleaned = df[col_status].astype(str).str.strip().str.lower()
        df = df[status_cleaned.isin(valid_statuses)].copy() # <- через copy() новая таблица

        # 3. Переводим суммы в числа и убираем нулевые операции
        df['Сумма_чистая'] = df[col_amount].apply(self._clean_money) # <- вызов "чистки"
        df = df[df['Сумма_чистая'] != 0].copy() # <- отброс мусора

        # 4. Заполняем пропуски, чтобы группировка по категориям и отчёт не падали на пустых ячейках
        if self.col_cat not in df.columns:
            df[self.col_cat] = 'Без категории'
        if self.col_desc not in df.columns:
            df[self.col_desc] = 'Без описания'

        df[self.col_cat] = df[self.col_cat].fillna('Без категории')
        df[self.col_desc] = df[self.col_desc].fillna('Без описания')

        # 5. Отделяем переводы от реальных расходов и доходов
        transit_flags = []
        for _, row in df.iterrows():
            transit_flags.append(self._is_transit_operation(row))

        transit_mask = pd.Series(transit_flags, index=df.index, dtype=bool)
        self.transit = df[transit_mask].copy()

        # Знак ~ инвертирует маску: берем все операции, которые НЕ являются переводами
        df_clean = df[~transit_mask].copy()
        self.expenses = df_clean[df_clean['Сумма_чистая'] < 0].copy()
        self.income = df_clean[df_clean['Сумма_чистая'] > 0].copy()

    def get_analytics(self):
        if self.expenses.empty: # <- если колонка пустая
            return None

        # Суммируем расходы по категориям и берем модуль, так как списания хранятся с минусом
        grouped_expenses = self.expenses.groupby(self.col_cat)['Сумма_чистая'].sum()
        category_sums = grouped_expenses.abs()

        sorted_expenses = self.expenses.sort_values(by='Сумма_чистая', ascending=True)
        top_5_expenses = sorted_expenses.head(5)

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